//! S2 acceptance: run the accepted E1 universal-embodiment validators (Core 33eb4b0)
//! on a Studio package. Read-only; prints a JSON report.
use finalverse_embodiment::universal::{Artifact, EmbodimentDefinition, Specification};
use sha2::{Digest, Sha256};
fn hex(b: &[u8]) -> String { Sha256::digest(b).iter().map(|x| format!("{x:02x}")).collect() }
fn main() {
    let dir = std::path::PathBuf::from(std::env::args().nth(1).expect("package dir"));
    let body = std::fs::read(dir.join("body.json")).unwrap();
    let spec_bytes = std::fs::read(dir.join("specification.json")).unwrap();
    let def_bytes = std::fs::read(dir.join("definition.draft.json")).unwrap();
    let as_is = Artifact::load(&body, &hex(&body)).err();
    let spec: Specification = serde_json::from_slice(&spec_bytes).unwrap();
    let spec_as_is = spec.validate().err();
    // Structural probe: identical document except the generator header, which E1
    // reserves for its own reviewed Blender worker. Clearly labelled, never exported.
    let text = String::from_utf8(body.clone()).unwrap().replacen("\"generator\":\"finalverse-studio-s2/1\"", "\"generator\":\"blender-universal/1\"", 1);
    let probe = text.as_bytes();
    let structural = Artifact::load(probe, &hex(probe));
    let mut def: EmbodimentDefinition = serde_json::from_slice(&def_bytes).unwrap();
    let (structural_ok, structural_err, definition_err) = match &structural {
        Ok(a) => { def.artifact_sha256 = hex(probe); (true, None, def.validate(a).err()) }
        Err(e) => (false, Some(e.clone()), None),
    };
    let lods = structural.as_ref().map(|a| a.lods().iter().map(|l| (l.distance_m, l.parts.len(), l.parts.iter().map(|p| p.indices.len()/3).sum::<usize>())).collect::<Vec<_>>()).unwrap_or_default();
    println!("{}", serde_json::json!({
        "schema_version": "finalverse.studio-s2-e1-check/v1",
        "core_validator": "finalverse-embodiment universal.rs @ 33eb4b0",
        "as_exported": {"artifact_error": as_is, "specification_error": spec_as_is},
        "structural_probe_generator_substituted": {"artifact_ok": structural_ok, "artifact_error": structural_err,
            "definition_error": definition_err, "lods": lods},
    }));
}
