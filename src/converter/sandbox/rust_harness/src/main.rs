//! Fixed runner for differential testing.
//!
//! Reads a JSON array of cases, calls `user_code::dispatch` for each one, catches
//! panics, and writes a JSON array of outcomes. This file is never authored by
//! the LLM.

mod error_prelude;
mod harness;
mod user_code;

use std::fs;
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::process::ExitCode;

use serde::Serialize;
use serde_json::Value;

use harness::Case;

#[derive(Serialize)]
#[serde(tag = "kind", rename_all = "lowercase")]
enum Outcome {
    Value { value: Value },
    Error {
        error_variant: String,
        message: String,
    },
    Panic,
}

#[derive(Serialize)]
struct ResultRow {
    test_id: String,
    #[serde(flatten)]
    outcome: Outcome,
}

fn main() -> ExitCode {
    let arguments: Vec<String> = std::env::args().collect();
    if arguments.len() < 3 {
        eprintln!("usage: converter_sandbox <cases.json> <results.json>");
        return ExitCode::from(2);
    }

    let cases_path = &arguments[1];
    let results_path = &arguments[2];

    let raw = match fs::read_to_string(cases_path) {
        Ok(raw) => raw,
        Err(error) => {
            eprintln!("could not read cases: {}", error);
            return ExitCode::from(2);
        }
    };
    let cases: Vec<Case> = match serde_json::from_str(&raw) {
        Ok(cases) => cases,
        Err(error) => {
            eprintln!("could not parse cases: {}", error);
            return ExitCode::from(2);
        }
    };

    let mut rows = Vec::with_capacity(cases.len());
    for case in &cases {
        let result = catch_unwind(AssertUnwindSafe(|| user_code::dispatch(case)));
        let outcome = match result {
            Ok(Ok(value)) => Outcome::Value { value },
            Ok(Err(error)) => Outcome::Error {
                error_variant: error.variant_name().to_string(),
                message: error.message().to_string(),
            },
            Err(_) => Outcome::Panic,
        };
        rows.push(ResultRow {
            test_id: case.test_id.clone(),
            outcome,
        });
    }

    let serialized = match serde_json::to_string(&rows) {
        Ok(serialized) => serialized,
        Err(error) => {
            eprintln!("could not serialize results: {}", error);
            return ExitCode::from(2);
        }
    };
    if let Err(error) = fs::write(results_path, serialized) {
        eprintln!("could not write results: {}", error);
        return ExitCode::from(2);
    }
    ExitCode::SUCCESS
}
