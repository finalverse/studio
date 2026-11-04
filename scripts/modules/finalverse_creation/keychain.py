# SPDX-FileCopyrightText: 2026 Finalverse Authors
# SPDX-License-Identifier: GPL-2.0-or-later
"""macOS Keychain storage for provider credentials.

Secrets go straight to Security.framework through ctypes: they never appear in
argv (unlike the `security` CLI), in providers.json, in .blend files, in job
receipts or in logs. Only the trusted Studio host process reads them, right
before it starts the network helper. The helper receives the one selected
secret in its private environment.
"""
import ctypes
import ctypes.util
import re
import sys

SERVICE = 'org.finalverse.studio.provider'
_ACCOUNT = re.compile(r'[a-z][a-z0-9_-]{0,31}')
errSecItemNotFound = -25300
errSecDuplicateItem = -25299


class KeychainError(RuntimeError):
    pass


def available():
    return sys.platform == 'darwin'


def _frameworks():
    if not available():
        raise KeychainError('The macOS Keychain is required for provider credentials')
    sec = ctypes.cdll.LoadLibrary(ctypes.util.find_library('Security'))
    cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library('CoreFoundation'))
    vp = ctypes.c_void_p
    cf.CFStringCreateWithCString.restype = vp
    cf.CFStringCreateWithCString.argtypes = [vp, ctypes.c_char_p, ctypes.c_uint32]
    cf.CFDataCreate.restype = vp
    cf.CFDataCreate.argtypes = [vp, ctypes.c_char_p, ctypes.c_long]
    cf.CFDataGetLength.restype = ctypes.c_long
    cf.CFDataGetLength.argtypes = [vp]
    cf.CFDataGetBytePtr.restype = vp
    cf.CFDataGetBytePtr.argtypes = [vp]
    cf.CFDictionaryCreate.restype = vp
    cf.CFDictionaryCreate.argtypes = [vp, ctypes.POINTER(vp), ctypes.POINTER(vp), ctypes.c_long, vp, vp]
    cf.CFRelease.argtypes = [vp]
    for name in ('SecItemAdd', 'SecItemCopyMatching', 'SecItemDelete'):
        getattr(sec, name).restype = ctypes.c_int32
    sec.SecItemAdd.argtypes = [vp, ctypes.POINTER(vp)]
    sec.SecItemCopyMatching.argtypes = [vp, ctypes.POINTER(vp)]
    sec.SecItemDelete.argtypes = [vp]
    sec.SecItemUpdate.restype = ctypes.c_int32
    sec.SecItemUpdate.argtypes = [vp, vp]
    return sec, cf


def _constant(lib, name):
    return ctypes.c_void_p.in_dll(lib, name).value


class _Query:
    def __init__(self, account, extra=()):
        if not isinstance(account, str) or not _ACCOUNT.fullmatch(account):
            raise KeychainError('Invalid provider credential account')
        self.sec, self.cf = _frameworks()
        self.owned = []
        utf8 = 0x08000100
        def text(value):
            ref = self.cf.CFStringCreateWithCString(None, value.encode(), utf8); self.owned.append(ref); return ref
        pairs = [('kSecClass', _constant(self.sec, 'kSecClassGenericPassword')),
                 ('kSecAttrService', text(SERVICE)), ('kSecAttrAccount', text(account)),
                 ('kSecAttrLabel', text('Finalverse Studio provider: ' + account))]
        pairs += list(extra(self) if callable(extra) else extra)
        self.ref = self.dictionary(pairs)

    def dictionary(self, pairs):
        keys = (ctypes.c_void_p*len(pairs))(*[_constant(self.sec, k) for k, _ in pairs])
        values = (ctypes.c_void_p*len(pairs))(*[v for _, v in pairs])
        ref = self.cf.CFDictionaryCreate(None, keys, values, len(pairs),
            ctypes.addressof(ctypes.c_char.in_dll(self.cf, 'kCFTypeDictionaryKeyCallBacks')),
            ctypes.addressof(ctypes.c_char.in_dll(self.cf, 'kCFTypeDictionaryValueCallBacks')))
        self.owned.append(ref)
        return ref

    def data(self, value):
        ref = self.cf.CFDataCreate(None, value, len(value)); self.owned.append(ref); return ref

    def close(self):
        for ref in reversed(self.owned):
            if ref:
                self.cf.CFRelease(ref)
        self.owned = []


def _check(status, action):
    if status != 0:
        raise KeychainError(f'Keychain {action} failed (OSStatus {status})')


def store(account, secret):
    if not isinstance(secret, str) or not 1 <= len(secret) <= 4096 or any(c in secret for c in '\r\n\0'):
        raise KeychainError('Credential must be 1–4096 characters on one line')
    raw = secret.encode()
    find = _Query(account)
    try:
        values = find.dictionary([('kSecValueData', find.data(raw))])
        status = find.sec.SecItemUpdate(find.ref, values)
        if status == errSecItemNotFound:
            add = _Query(account, lambda q: [('kSecValueData', q.data(raw))])
            try:
                _check(add.sec.SecItemAdd(add.ref, None), 'add')
            finally:
                add.close()
        else:
            _check(status, 'update')
    finally:
        find.close()


def read(account):
    """Return the secret, or None when no item exists."""
    def attributes(q):
        return [('kSecReturnData', _constant(q.cf, 'kCFBooleanTrue')),
                ('kSecMatchLimit', _constant(q.sec, 'kSecMatchLimitOne'))]
    query = _Query(account, attributes)
    try:
        result = ctypes.c_void_p()
        status = query.sec.SecItemCopyMatching(query.ref, ctypes.byref(result))
        if status == errSecItemNotFound:
            return None
        _check(status, 'read')
        try:
            size = query.cf.CFDataGetLength(result)
            return ctypes.string_at(query.cf.CFDataGetBytePtr(result), size).decode()
        finally:
            query.cf.CFRelease(result)
    finally:
        query.close()


def exists(account):
    return read(account) is not None


def delete(account):
    query = _Query(account)
    try:
        status = query.sec.SecItemDelete(query.ref)
        if status not in (0, errSecItemNotFound):
            _check(status, 'delete')
        return status == 0
    finally:
        query.close()
