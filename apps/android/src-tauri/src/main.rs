// Desktop entry point. Mobile targets enter through `aiol_client_lib::run` via the generated mobile projects.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    aiol_client_lib::run()
}
