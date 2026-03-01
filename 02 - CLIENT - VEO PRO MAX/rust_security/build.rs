use std::env;
use std::fs;
use std::path::PathBuf;

fn main() {
    // Generate build timestamp
    let out_dir = PathBuf::from(env::var("OUT_DIR").unwrap());
    let timestamp = chrono::Utc::now().to_rfc3339();
    fs::write(out_dir.join("build_ts.txt"), &timestamp).unwrap();
    println!("cargo:rerun-if-changed=src/lib.rs");
}
