// Injected into every generated Rust crate. This is the Rust half of the
// error-mapping convention defined in errors_map/mapping.py.

#[derive(Debug, Clone, PartialEq)]
pub enum ConvError {
    ValueError(String),
    TypeError(String),
    KeyError(String),
    IndexError(String),
    ZeroDivisionError(String),
    OverflowError(String),
    ArithmeticError(String),
    AssertionError(String),
    RuntimeError(String),
    Other { python_type: String, message: String },
}

impl ConvError {
    /// The variant name compared by the differential verifier.
    pub fn variant_name(&self) -> &'static str {
        match self {
            ConvError::ValueError(_) => "ValueError",
            ConvError::TypeError(_) => "TypeError",
            ConvError::KeyError(_) => "KeyError",
            ConvError::IndexError(_) => "IndexError",
            ConvError::ZeroDivisionError(_) => "ZeroDivisionError",
            ConvError::OverflowError(_) => "OverflowError",
            ConvError::ArithmeticError(_) => "ArithmeticError",
            ConvError::AssertionError(_) => "AssertionError",
            ConvError::RuntimeError(_) => "RuntimeError",
            ConvError::Other { .. } => "Other",
        }
    }

    /// Message text used for optional message-pattern checks.
    pub fn message(&self) -> &str {
        match self {
            ConvError::ValueError(message)
            | ConvError::TypeError(message)
            | ConvError::KeyError(message)
            | ConvError::IndexError(message)
            | ConvError::ZeroDivisionError(message)
            | ConvError::OverflowError(message)
            | ConvError::ArithmeticError(message)
            | ConvError::AssertionError(message)
            | ConvError::RuntimeError(message) => message,
            ConvError::Other { message, .. } => message,
        }
    }
}

impl std::fmt::Display for ConvError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ConvError::Other { python_type, message } => {
                write!(formatter, "{}: {}", python_type, message)
            }
            _ => write!(formatter, "{}: {}", self.variant_name(), self.message()),
        }
    }
}

impl std::error::Error for ConvError {}
