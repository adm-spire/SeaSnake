//! Fixed harness types and helpers shared with generated user code.
//!
//! The LLM writes `user_code.rs`, which must expose:
//!
//! ```ignore
//! pub fn dispatch(
//!     case: &crate::harness::Case,
//! ) -> Result<serde_json::Value, crate::error_prelude::ConvError>
//! ```
//!
//! Everything else in this file is owned by the converter, not the LLM.

use std::collections::BTreeMap;

use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::error_prelude::ConvError;

#[derive(Debug, Clone, Deserialize)]
pub struct Case {
    pub test_id: String,
    pub function: String,
    #[serde(default)]
    pub args: Vec<Value>,
    #[serde(default)]
    pub kwargs: BTreeMap<String, Value>,
}

/// Read a positional argument and deserialize it into the expected Rust type.
pub fn arg<T: DeserializeOwned>(case: &Case, index: usize) -> Result<T, ConvError> {
    let value = case.args.get(index).ok_or_else(|| {
        ConvError::IndexError(format!("missing positional argument at index {}", index))
    })?;
    serde_json::from_value(value.clone()).map_err(|error| {
        ConvError::TypeError(format!(
            "argument {} has the wrong type: {}",
            index, error
        ))
    })
}

/// Read an optional positional argument. Missing or JSON null becomes None.
pub fn opt_arg<T: DeserializeOwned>(case: &Case, index: usize) -> Result<Option<T>, ConvError> {
    match case.args.get(index) {
        None | Some(Value::Null) => Ok(None),
        Some(value) => serde_json::from_value(value.clone())
            .map(Some)
            .map_err(|error| {
                ConvError::TypeError(format!(
                    "argument {} has the wrong type: {}",
                    index, error
                ))
            }),
    }
}

/// Read a required parameter that may arrive positionally or by keyword.
///
/// Python's calling convention allows either form, so dispatch should use this
/// helper rather than only `arg` for required parameters.
pub fn req_arg<T: DeserializeOwned>(
    case: &Case,
    index: usize,
    name: &str,
) -> Result<T, ConvError> {
    if let Some(value) = case.args.get(index) {
        return serde_json::from_value(value.clone()).map_err(|error| {
            ConvError::TypeError(format!("argument '{}' has the wrong type: {}", name, error))
        });
    }
    if let Some(value) = case.kwargs.get(name) {
        return serde_json::from_value(value.clone()).map_err(|error| {
            ConvError::TypeError(format!(
                "keyword argument '{}' has the wrong type: {}",
                name, error
            ))
        });
    }
    Err(ConvError::TypeError(format!(
        "missing required argument '{}'",
        name
    )))
}

/// Read an optional/defaulted parameter that may arrive positionally or by keyword.
pub fn opt_named_arg<T: DeserializeOwned>(
    case: &Case,
    index: usize,
    name: &str,
) -> Result<Option<T>, ConvError> {
    if let Some(value) = case.args.get(index) {
        if value.is_null() {
            return Ok(None);
        }
        return serde_json::from_value(value.clone())
            .map(Some)
            .map_err(|error| {
                ConvError::TypeError(format!(
                    "argument '{}' has the wrong type: {}",
                    name, error
                ))
            });
    }
    if let Some(value) = case.kwargs.get(name) {
        if value.is_null() {
            return Ok(None);
        }
        return serde_json::from_value(value.clone())
            .map(Some)
            .map_err(|error| {
                ConvError::TypeError(format!(
                    "keyword argument '{}' has the wrong type: {}",
                    name, error
                ))
            });
    }
    Ok(None)
}

/// Reject unexpected keyword arguments, matching Python's TypeErrors.
pub fn ensure_kwargs(case: &Case, allowed: &[&str]) -> Result<(), ConvError> {
    for key in case.kwargs.keys() {
        if !allowed.contains(&key.as_str()) {
            return Err(ConvError::TypeError(format!(
                "unexpected keyword argument '{}'",
                key
            )));
        }
    }
    Ok(())
}

/// Read a keyword argument and deserialize it into the expected Rust type.
pub fn kwarg<T: DeserializeOwned>(case: &Case, name: &str) -> Result<T, ConvError> {
    let value = case.kwargs.get(name).ok_or_else(|| {
        ConvError::KeyError(format!("missing keyword argument '{}'", name))
    })?;
    serde_json::from_value(value.clone()).map_err(|error| {
        ConvError::TypeError(format!(
            "keyword argument '{}' has the wrong type: {}",
            name, error
        ))
    })
}

/// Read an optional keyword argument. Missing or JSON null becomes None.
pub fn opt_kwarg<T: DeserializeOwned>(case: &Case, name: &str) -> Result<Option<T>, ConvError> {
    match case.kwargs.get(name) {
        None | Some(Value::Null) => Ok(None),
        Some(value) => serde_json::from_value(value.clone())
            .map(Some)
            .map_err(|error| {
                ConvError::TypeError(format!(
                    "keyword argument '{}' has the wrong type: {}",
                    name, error
                ))
            }),
    }
}

/// Serialize a Rust return value into the JSON contract.
pub fn json<T: Serialize>(value: T) -> Result<Value, ConvError> {
    serde_json::to_value(value).map_err(|error| {
        ConvError::TypeError(format!("return value could not be serialized: {}", error))
    })
}
