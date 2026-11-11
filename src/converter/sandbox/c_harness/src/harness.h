/*
 * Fixed harness types and helpers shared with generated user code.
 *
 * The LLM writes `src/user_code.c`, which must expose:
 *
 *     ConvResult dispatch(const Case *test_case);
 *
 * Everything else here is owned by the converter, not the LLM.
 */

#ifndef CONVERTER_HARNESS_H
#define CONVERTER_HARNESS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>

#include "error_prelude.h"

typedef enum {
    JSON_NULL = 0,
    JSON_BOOL,
    JSON_INT,
    JSON_FLOAT,
    JSON_STRING,
    JSON_ARRAY,
    JSON_OBJECT
} JsonKind;

typedef struct JsonValue JsonValue;

typedef struct {
    const char *test_id;
    const char *function;
    JsonValue *args;   /* JSON_ARRAY */
    JsonValue *kwargs; /* JSON_OBJECT */
} Case;

typedef struct {
    bool ok;          /* true: value is set; false: error is set */
    JsonValue *value; /* owned by the harness arena */
    ConvError error;
} ConvResult;

/* ---- results ---------------------------------------------------------- */

ConvResult conv_ok(JsonValue *value);
ConvResult conv_error(ConvErrorKind kind, const char *message);
ConvResult conv_other(const char *python_type, const char *message);
ConvResult conv_fail(ConvError error);

/* ---- value construction ---------------------------------------------- */

JsonValue *value_null(void);
JsonValue *value_bool(bool value);
JsonValue *value_int(long long value);
JsonValue *value_double(double value);
JsonValue *value_string(const char *value);
JsonValue *value_array(void);
void array_push(JsonValue *array, JsonValue *item);
JsonValue *value_object(void);
void object_set(JsonValue *object, const char *key, JsonValue *item);

/* ---- value inspection ------------------------------------------------ */

JsonKind value_kind(const JsonValue *value);
size_t value_length(const JsonValue *value);
JsonValue *value_index(const JsonValue *value, size_t index);
JsonValue *object_get(const JsonValue *value, const char *key);
const char *value_as_string(const JsonValue *value);
long long value_as_int(const JsonValue *value);
double value_as_double(const JsonValue *value);
bool value_as_bool(const JsonValue *value);
bool value_is_null(const JsonValue *value);

/* ---- argument resolution --------------------------------------------- */

/* Positional argument when present, else keyword argument, else NULL. */
JsonValue *arg_value(const Case *test_case, size_t index, const char *name);

bool arg_int(const Case *test_case, size_t index, const char *name,
             long long *out, ConvError *error);
bool arg_double(const Case *test_case, size_t index, const char *name,
                double *out, ConvError *error);
bool arg_bool(const Case *test_case, size_t index, const char *name,
              bool *out, ConvError *error);
bool arg_string(const Case *test_case, size_t index, const char *name,
                const char **out, ConvError *error);

bool ensure_kwargs(const Case *test_case, const char *const *allowed, size_t count,
                   ConvError *error);

/* ---- JSON I/O (used by main.c) --------------------------------------- */

JsonValue *json_parse(const char *text);
void json_write(FILE *out, const JsonValue *value);

#endif /* CONVERTER_HARNESS_H */
