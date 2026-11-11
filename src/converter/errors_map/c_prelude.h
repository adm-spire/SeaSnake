/*
 * Injected into every generated C project. This is the C half of the
 * error-mapping convention defined in errors_map/mapping.py.
 *
 * A translation never throws; it returns a ConvResult carrying either a JSON
 * value or one of these error variants. The harness reports the variant name to
 * the Python differential verifier.
 */

#ifndef CONVERTER_ERROR_PRELUDE_H
#define CONVERTER_ERROR_PRELUDE_H

typedef enum {
    CONV_VALUE_ERROR = 0,
    CONV_TYPE_ERROR,
    CONV_KEY_ERROR,
    CONV_INDEX_ERROR,
    CONV_ZERO_DIVISION_ERROR,
    CONV_OVERFLOW_ERROR,
    CONV_ARITHMETIC_ERROR,
    CONV_ASSERTION_ERROR,
    CONV_RUNTIME_ERROR,
    CONV_OTHER
} ConvErrorKind;

typedef struct {
    ConvErrorKind kind;
    char message[512];
    char python_type[64];
} ConvError;

/* Variant name compared by the differential verifier, e.g. "ValueError". */
const char *conv_error_variant(ConvErrorKind kind);

#endif /* CONVERTER_ERROR_PRELUDE_H */
