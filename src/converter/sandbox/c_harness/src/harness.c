/*
 * Converter-owned C harness: a small JSON reader/writer, a dynamic Value type,
 * the argument-resolution helpers, and the ConvResult helpers.
 *
 * This file is never authored by the LLM. It only implements the fixed contract
 * documented in harness.h.
 */

#include "harness.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

struct JsonValue {
    JsonKind kind;
    union {
        bool boolean;
        long long integer;
        double number;
        struct {
            char *data;
            size_t len;
        } string;
        struct {
            JsonValue **items;
            size_t len;
            size_t cap;
        } array;
        struct {
            char **keys;
            JsonValue **values;
            size_t len;
            size_t cap;
        } object;
    } as;
};

/* ---- allocation ------------------------------------------------------- */

static void *xmalloc(size_t size) {
    void *pointer = malloc(size ? size : 1);
    if (pointer == NULL) {
        fputs("harness: out of memory\n", stderr);
        exit(3);
    }
    return pointer;
}

static void *xrealloc(void *pointer, size_t size) {
    void *resized = realloc(pointer, size ? size : 1);
    if (resized == NULL) {
        fputs("harness: out of memory\n", stderr);
        exit(3);
    }
    return resized;
}

static char *xstrdup(const char *text) {
    size_t length = strlen(text);
    char *copy = xmalloc(length + 1);
    memcpy(copy, text, length + 1);
    return copy;
}

static JsonValue *new_value(JsonKind kind) {
    JsonValue *value = xmalloc(sizeof(*value));
    memset(value, 0, sizeof(*value));
    value->kind = kind;
    return value;
}

/* ---- error variants --------------------------------------------------- */

const char *conv_error_variant(ConvErrorKind kind) {
    switch (kind) {
        case CONV_VALUE_ERROR:
            return "ValueError";
        case CONV_TYPE_ERROR:
            return "TypeError";
        case CONV_KEY_ERROR:
            return "KeyError";
        case CONV_INDEX_ERROR:
            return "IndexError";
        case CONV_ZERO_DIVISION_ERROR:
            return "ZeroDivisionError";
        case CONV_OVERFLOW_ERROR:
            return "OverflowError";
        case CONV_ARITHMETIC_ERROR:
            return "ArithmeticError";
        case CONV_ASSERTION_ERROR:
            return "AssertionError";
        case CONV_RUNTIME_ERROR:
            return "RuntimeError";
        case CONV_OTHER:
        default:
            return "Other";
    }
}

/* ---- result helpers --------------------------------------------------- */

ConvResult conv_ok(JsonValue *value) {
    ConvResult result;
    memset(&result, 0, sizeof(result));
    result.ok = true;
    result.value = value;
    return result;
}

ConvResult conv_error(ConvErrorKind kind, const char *message) {
    ConvResult result;
    memset(&result, 0, sizeof(result));
    result.ok = false;
    result.error.kind = kind;
    if (message != NULL) {
        strncpy(result.error.message, message, sizeof(result.error.message) - 1);
    }
    return result;
}

ConvResult conv_other(const char *python_type, const char *message) {
    ConvResult result = conv_error(CONV_OTHER, message);
    if (python_type != NULL) {
        strncpy(result.error.python_type, python_type,
                sizeof(result.error.python_type) - 1);
    }
    return result;
}

ConvResult conv_fail(ConvError error) {
    ConvResult result;
    memset(&result, 0, sizeof(result));
    result.ok = false;
    result.error = error;
    return result;
}

/* ---- value construction ---------------------------------------------- */

JsonValue *value_null(void) { return new_value(JSON_NULL); }

JsonValue *value_bool(bool value) {
    JsonValue *result = new_value(JSON_BOOL);
    result->as.boolean = value;
    return result;
}

JsonValue *value_int(long long value) {
    JsonValue *result = new_value(JSON_INT);
    result->as.integer = value;
    return result;
}

JsonValue *value_double(double value) {
    JsonValue *result = new_value(JSON_FLOAT);
    result->as.number = value;
    return result;
}

JsonValue *value_string(const char *value) {
    JsonValue *result = new_value(JSON_STRING);
    size_t length = value == NULL ? 0 : strlen(value);
    result->as.string.data = xmalloc(length + 1);
    if (length > 0) {
        memcpy(result->as.string.data, value, length);
    }
    result->as.string.data[length] = '\0';
    result->as.string.len = length;
    return result;
}

JsonValue *value_array(void) { return new_value(JSON_ARRAY); }

void array_push(JsonValue *array, JsonValue *item) {
    if (array == NULL || array->kind != JSON_ARRAY) {
        return;
    }
    if (array->as.array.len == array->as.array.cap) {
        size_t cap = array->as.array.cap == 0 ? 4 : array->as.array.cap * 2;
        array->as.array.items =
            xrealloc(array->as.array.items, cap * sizeof(*array->as.array.items));
        array->as.array.cap = cap;
    }
    array->as.array.items[array->as.array.len++] = item;
}

JsonValue *value_object(void) { return new_value(JSON_OBJECT); }

void object_set(JsonValue *object, const char *key, JsonValue *item) {
    if (object == NULL || object->kind != JSON_OBJECT || key == NULL) {
        return;
    }
    for (size_t index = 0; index < object->as.object.len; index++) {
        if (strcmp(object->as.object.keys[index], key) == 0) {
            object->as.object.values[index] = item;
            return;
        }
    }
    if (object->as.object.len == object->as.object.cap) {
        size_t cap = object->as.object.cap == 0 ? 4 : object->as.object.cap * 2;
        object->as.object.keys =
            xrealloc(object->as.object.keys, cap * sizeof(*object->as.object.keys));
        object->as.object.values = xrealloc(
            object->as.object.values, cap * sizeof(*object->as.object.values));
        object->as.object.cap = cap;
    }
    size_t slot = object->as.object.len++;
    object->as.object.keys[slot] = xstrdup(key);
    object->as.object.values[slot] = item;
}

/* ---- value inspection ------------------------------------------------- */

JsonKind value_kind(const JsonValue *value) {
    return value == NULL ? JSON_NULL : value->kind;
}

size_t value_length(const JsonValue *value) {
    if (value == NULL) {
        return 0;
    }
    switch (value->kind) {
        case JSON_STRING:
            return value->as.string.len;
        case JSON_ARRAY:
            return value->as.array.len;
        case JSON_OBJECT:
            return value->as.object.len;
        default:
            return 0;
    }
}

JsonValue *value_index(const JsonValue *value, size_t index) {
    if (value == NULL || value->kind != JSON_ARRAY ||
        index >= value->as.array.len) {
        return NULL;
    }
    return value->as.array.items[index];
}

JsonValue *object_get(const JsonValue *value, const char *key) {
    if (value == NULL || value->kind != JSON_OBJECT || key == NULL) {
        return NULL;
    }
    for (size_t index = 0; index < value->as.object.len; index++) {
        if (strcmp(value->as.object.keys[index], key) == 0) {
            return value->as.object.values[index];
        }
    }
    return NULL;
}

const char *value_as_string(const JsonValue *value) {
    if (value == NULL || value->kind != JSON_STRING) {
        return NULL;
    }
    return value->as.string.data;
}

long long value_as_int(const JsonValue *value) {
    if (value == NULL || value->kind != JSON_INT) {
        return 0;
    }
    return value->as.integer;
}

double value_as_double(const JsonValue *value) {
    if (value == NULL) {
        return 0.0;
    }
    if (value->kind == JSON_INT) {
        return (double)value->as.integer;
    }
    if (value->kind == JSON_FLOAT) {
        return value->as.number;
    }
    return 0.0;
}

bool value_as_bool(const JsonValue *value) {
    return value != NULL && value->kind == JSON_BOOL && value->as.boolean;
}

bool value_is_null(const JsonValue *value) {
    return value == NULL || value->kind == JSON_NULL;
}

/* ---- argument resolution --------------------------------------------- */

static JsonValue *resolve_arg(const Case *test_case, size_t index, const char *name) {
    if (test_case == NULL) {
        return NULL;
    }
    if (test_case->args != NULL && test_case->args->kind == JSON_ARRAY &&
        index < test_case->args->as.array.len) {
        return test_case->args->as.array.items[index];
    }
    if (test_case->kwargs != NULL && name != NULL) {
        return object_get(test_case->kwargs, name);
    }
    return NULL;
}

JsonValue *arg_value(const Case *test_case, size_t index, const char *name) {
    return resolve_arg(test_case, index, name);
}

static void set_missing(ConvError *error, const char *name) {
    if (error == NULL) {
        return;
    }
    error->kind = CONV_TYPE_ERROR;
    snprintf(error->message, sizeof(error->message),
             "missing required argument '%s'", name);
}

static void set_wrong_type(ConvError *error, const char *name,
                           const char *expected) {
    if (error == NULL) {
        return;
    }
    error->kind = CONV_TYPE_ERROR;
    snprintf(error->message, sizeof(error->message),
             "argument '%s' has the wrong type (expected %s)", name, expected);
}

bool arg_int(const Case *test_case, size_t index, const char *name, long long *out,
             ConvError *error) {
    JsonValue *value = resolve_arg(test_case, index, name);
    if (value == NULL) {
        set_missing(error, name);
        return false;
    }
    if (value->kind != JSON_INT) {
        set_wrong_type(error, name, "int");
        return false;
    }
    *out = value->as.integer;
    return true;
}

bool arg_double(const Case *test_case, size_t index, const char *name, double *out,
                ConvError *error) {
    JsonValue *value = resolve_arg(test_case, index, name);
    if (value == NULL) {
        set_missing(error, name);
        return false;
    }
    if (value->kind == JSON_INT) {
        *out = (double)value->as.integer;
        return true;
    }
    if (value->kind == JSON_FLOAT) {
        *out = value->as.number;
        return true;
    }
    set_wrong_type(error, name, "float");
    return false;
}

bool arg_bool(const Case *test_case, size_t index, const char *name, bool *out,
              ConvError *error) {
    JsonValue *value = resolve_arg(test_case, index, name);
    if (value == NULL) {
        set_missing(error, name);
        return false;
    }
    if (value->kind != JSON_BOOL) {
        set_wrong_type(error, name, "bool");
        return false;
    }
    *out = value->as.boolean;
    return true;
}

bool arg_string(const Case *test_case, size_t index, const char *name,
                const char **out, ConvError *error) {
    JsonValue *value = resolve_arg(test_case, index, name);
    if (value == NULL) {
        set_missing(error, name);
        return false;
    }
    if (value->kind != JSON_STRING) {
        set_wrong_type(error, name, "str");
        return false;
    }
    *out = value->as.string.data;
    return true;
}

bool ensure_kwargs(const Case *test_case, const char *const *allowed, size_t count,
                   ConvError *error) {
    if (test_case == NULL || test_case->kwargs == NULL ||
        test_case->kwargs->kind != JSON_OBJECT) {
        return true;
    }
    for (size_t index = 0; index < test_case->kwargs->as.object.len; index++) {
        const char *key = test_case->kwargs->as.object.keys[index];
        bool known = false;
        for (size_t allowed_index = 0; allowed_index < count; allowed_index++) {
            if (strcmp(key, allowed[allowed_index]) == 0) {
                known = true;
                break;
            }
        }
        if (!known) {
            if (error != NULL) {
                error->kind = CONV_TYPE_ERROR;
                snprintf(error->message, sizeof(error->message),
                         "unexpected keyword argument '%s'", key);
            }
            return false;
        }
    }
    return true;
}

/* ---- JSON parser ------------------------------------------------------ */

typedef struct {
    const char *cursor;
    const char *end;
    bool failed;
} Parser;

static void skip_whitespace(Parser *parser) {
    while (parser->cursor < parser->end) {
        char character = *parser->cursor;
        if (character == ' ' || character == '\t' || character == '\n' ||
            character == '\r') {
            parser->cursor++;
        } else {
            break;
        }
    }
}

static void buffer_reserve(char **buffer, size_t *capacity, size_t needed) {
    if (needed <= *capacity) {
        return;
    }
    size_t cap = *capacity == 0 ? 16 : *capacity;
    while (cap < needed) {
        cap *= 2;
    }
    *buffer = xrealloc(*buffer, cap);
    *capacity = cap;
}

static void buffer_byte(char **buffer, size_t *length, size_t *capacity,
                        unsigned char byte) {
    buffer_reserve(buffer, capacity, *length + 2);
    (*buffer)[(*length)++] = (char)byte;
}

static void buffer_codepoint(char **buffer, size_t *length, size_t *capacity,
                             unsigned codepoint) {
    if (codepoint <= 0x7F) {
        buffer_byte(buffer, length, capacity, (unsigned char)codepoint);
    } else if (codepoint <= 0x7FF) {
        buffer_byte(buffer, length, capacity,
                    (unsigned char)(0xC0 | (codepoint >> 6)));
        buffer_byte(buffer, length, capacity,
                    (unsigned char)(0x80 | (codepoint & 0x3F)));
    } else if (codepoint <= 0xFFFF) {
        buffer_byte(buffer, length, capacity,
                    (unsigned char)(0xE0 | (codepoint >> 12)));
        buffer_byte(buffer, length, capacity,
                    (unsigned char)(0x80 | ((codepoint >> 6) & 0x3F)));
        buffer_byte(buffer, length, capacity,
                    (unsigned char)(0x80 | (codepoint & 0x3F)));
    } else {
        buffer_byte(buffer, length, capacity,
                    (unsigned char)(0xF0 | (codepoint >> 18)));
        buffer_byte(buffer, length, capacity,
                    (unsigned char)(0x80 | ((codepoint >> 12) & 0x3F)));
        buffer_byte(buffer, length, capacity,
                    (unsigned char)(0x80 | ((codepoint >> 6) & 0x3F)));
        buffer_byte(buffer, length, capacity,
                    (unsigned char)(0x80 | (codepoint & 0x3F)));
    }
}

static unsigned parse_hex4(Parser *parser) {
    unsigned value = 0;
    if (parser->end - parser->cursor < 4) {
        parser->failed = true;
        return 0;
    }
    for (int index = 0; index < 4; index++) {
        char character = *parser->cursor++;
        value <<= 4;
        if (character >= '0' && character <= '9') {
            value |= (unsigned)(character - '0');
        } else if (character >= 'a' && character <= 'f') {
            value |= (unsigned)(character - 'a' + 10);
        } else if (character >= 'A' && character <= 'F') {
            value |= (unsigned)(character - 'A' + 10);
        } else {
            parser->failed = true;
            return 0;
        }
    }
    return value;
}

static JsonValue *parse_string_value(Parser *parser) {
    if (parser->cursor >= parser->end || *parser->cursor != '"') {
        parser->failed = true;
        return NULL;
    }
    parser->cursor++;

    size_t length = 0;
    size_t capacity = 0;
    char *buffer = NULL;
    bool closed = false;

    while (parser->cursor < parser->end) {
        unsigned char character = (unsigned char)*parser->cursor++;
        if (character == '"') {
            closed = true;
            break;
        }
        if (character != '\\') {
            buffer_byte(&buffer, &length, &capacity, character);
            continue;
        }

        if (parser->cursor >= parser->end) {
            parser->failed = true;
            break;
        }
        char escape = *parser->cursor++;
        switch (escape) {
            case '"':
                buffer_byte(&buffer, &length, &capacity, '"');
                break;
            case '\\':
                buffer_byte(&buffer, &length, &capacity, '\\');
                break;
            case '/':
                buffer_byte(&buffer, &length, &capacity, '/');
                break;
            case 'b':
                buffer_byte(&buffer, &length, &capacity, '\b');
                break;
            case 'f':
                buffer_byte(&buffer, &length, &capacity, '\f');
                break;
            case 'n':
                buffer_byte(&buffer, &length, &capacity, '\n');
                break;
            case 'r':
                buffer_byte(&buffer, &length, &capacity, '\r');
                break;
            case 't':
                buffer_byte(&buffer, &length, &capacity, '\t');
                break;
            case 'u': {
                unsigned codepoint = parse_hex4(parser);
                if (parser->failed) {
                    break;
                }
                if (codepoint >= 0xD800 && codepoint <= 0xDBFF &&
                    parser->end - parser->cursor >= 6 &&
                    parser->cursor[0] == '\\' && parser->cursor[1] == 'u') {
                    parser->cursor += 2;
                    unsigned low = parse_hex4(parser);
                    if (!parser->failed && low >= 0xDC00 && low <= 0xDFFF) {
                        codepoint = 0x10000u +
                                    ((codepoint - 0xD800u) << 10) +
                                    (low - 0xDC00u);
                    }
                }
                if (!parser->failed) {
                    buffer_codepoint(&buffer, &length, &capacity, codepoint);
                }
                break;
            }
            default:
                parser->failed = true;
                break;
        }
        if (parser->failed) {
            break;
        }
    }

    if (!closed) {
        parser->failed = true;
    }
    if (parser->failed) {
        free(buffer);
        return NULL;
    }

    buffer_reserve(&buffer, &capacity, length + 1);
    buffer[length] = '\0';

    JsonValue *value = new_value(JSON_STRING);
    value->as.string.data = buffer;
    value->as.string.len = length;
    return value;
}

static JsonValue *parse_value(Parser *parser, int depth);

static JsonValue *parse_array_value(Parser *parser, int depth) {
    parser->cursor++; /* '[' */
    JsonValue *array = value_array();
    skip_whitespace(parser);
    if (parser->cursor < parser->end && *parser->cursor == ']') {
        parser->cursor++;
        return array;
    }
    while (parser->cursor < parser->end) {
        JsonValue *item = parse_value(parser, depth + 1);
        if (parser->failed) {
            return array;
        }
        array_push(array, item);
        skip_whitespace(parser);
        if (parser->cursor >= parser->end) {
            parser->failed = true;
            return array;
        }
        if (*parser->cursor == ',') {
            parser->cursor++;
            continue;
        }
        if (*parser->cursor == ']') {
            parser->cursor++;
            return array;
        }
        parser->failed = true;
        return array;
    }
    parser->failed = true;
    return array;
}

static JsonValue *parse_object_value(Parser *parser, int depth) {
    parser->cursor++; /* '{' */
    JsonValue *object = value_object();
    skip_whitespace(parser);
    if (parser->cursor < parser->end && *parser->cursor == '}') {
        parser->cursor++;
        return object;
    }
    while (parser->cursor < parser->end) {
        skip_whitespace(parser);
        JsonValue *key_value = parse_string_value(parser);
        if (parser->failed || key_value == NULL) {
            return object;
        }
        char *key = key_value->as.string.data;
        free(key_value);

        skip_whitespace(parser);
        if (parser->cursor >= parser->end || *parser->cursor != ':') {
            parser->failed = true;
            free(key);
            return object;
        }
        parser->cursor++;

        JsonValue *item = parse_value(parser, depth + 1);
        if (parser->failed) {
            free(key);
            return object;
        }
        object_set(object, key, item);
        free(key);

        skip_whitespace(parser);
        if (parser->cursor >= parser->end) {
            parser->failed = true;
            return object;
        }
        if (*parser->cursor == ',') {
            parser->cursor++;
            continue;
        }
        if (*parser->cursor == '}') {
            parser->cursor++;
            return object;
        }
        parser->failed = true;
        return object;
    }
    parser->failed = true;
    return object;
}

static JsonValue *parse_number_value(Parser *parser) {
    const char *start = parser->cursor;
    while (parser->cursor < parser->end) {
        char character = *parser->cursor;
        if ((character >= '0' && character <= '9') || character == '-' ||
            character == '+' || character == '.' || character == 'e' ||
            character == 'E') {
            parser->cursor++;
        } else {
            break;
        }
    }
    size_t length = (size_t)(parser->cursor - start);
    if (length == 0 || length >= 63) {
        parser->failed = true;
        return NULL;
    }
    char token[64];
    memcpy(token, start, length);
    token[length] = '\0';

    JsonValue *value;
    if (strpbrk(token, ".eE") != NULL) {
        value = value_double(strtod(token, NULL));
    } else {
        value = value_int(strtoll(token, NULL, 10));
    }
    return value;
}

static JsonValue *parse_value(Parser *parser, int depth) {
    if (depth > 256) {
        parser->failed = true;
        return NULL;
    }
    skip_whitespace(parser);
    if (parser->cursor >= parser->end) {
        parser->failed = true;
        return NULL;
    }

    char character = *parser->cursor;
    if (character == '"') {
        return parse_string_value(parser);
    }
    if (character == '[') {
        return parse_array_value(parser, depth);
    }
    if (character == '{') {
        return parse_object_value(parser, depth);
    }
    if (character == '-' || (character >= '0' && character <= '9')) {
        return parse_number_value(parser);
    }
    if (parser->end - parser->cursor >= 4 &&
        memcmp(parser->cursor, "null", 4) == 0) {
        parser->cursor += 4;
        return value_null();
    }
    if (parser->end - parser->cursor >= 4 &&
        memcmp(parser->cursor, "true", 4) == 0) {
        parser->cursor += 4;
        return value_bool(true);
    }
    if (parser->end - parser->cursor >= 5 &&
        memcmp(parser->cursor, "false", 5) == 0) {
        parser->cursor += 5;
        return value_bool(false);
    }

    parser->failed = true;
    return NULL;
}

JsonValue *json_parse(const char *text) {
    if (text == NULL) {
        return NULL;
    }
    Parser parser;
    parser.cursor = text;
    parser.end = text + strlen(text);
    parser.failed = false;

    JsonValue *root = parse_value(&parser, 0);
    if (parser.failed) {
        return NULL;
    }
    skip_whitespace(&parser);
    if (parser.cursor != parser.end) {
        return NULL;
    }
    return root;
}

/* ---- JSON writer ------------------------------------------------------ */

static void write_string(FILE *out, const char *text, size_t length) {
    fputc('"', out);
    for (size_t index = 0; index < length; index++) {
        unsigned char character = (unsigned char)text[index];
        switch (character) {
            case '"':
                fputs("\\\"", out);
                break;
            case '\\':
                fputs("\\\\", out);
                break;
            case '\b':
                fputs("\\b", out);
                break;
            case '\f':
                fputs("\\f", out);
                break;
            case '\n':
                fputs("\\n", out);
                break;
            case '\r':
                fputs("\\r", out);
                break;
            case '\t':
                fputs("\\t", out);
                break;
            default:
                if (character < 0x20) {
                    fprintf(out, "\\u%04x", (unsigned)character);
                } else {
                    fputc((int)character, out);
                }
                break;
        }
    }
    fputc('"', out);
}

void json_write(FILE *out, const JsonValue *value) {
    if (value == NULL) {
        fputs("null", out);
        return;
    }
    switch (value->kind) {
        case JSON_NULL:
            fputs("null", out);
            break;
        case JSON_BOOL:
            fputs(value->as.boolean ? "true" : "false", out);
            break;
        case JSON_INT:
            fprintf(out, "%lld", value->as.integer);
            break;
        case JSON_FLOAT:
            if (isfinite(value->as.number)) {
                fprintf(out, "%.17g", value->as.number);
            } else {
                fputs("null", out);
            }
            break;
        case JSON_STRING:
            write_string(out, value->as.string.data, value->as.string.len);
            break;
        case JSON_ARRAY:
            fputc('[', out);
            for (size_t index = 0; index < value->as.array.len; index++) {
                if (index > 0) {
                    fputc(',', out);
                }
                json_write(out, value->as.array.items[index]);
            }
            fputc(']', out);
            break;
        case JSON_OBJECT:
            fputc('{', out);
            for (size_t index = 0; index < value->as.object.len; index++) {
                if (index > 0) {
                    fputc(',', out);
                }
                const char *key = value->as.object.keys[index];
                write_string(out, key, strlen(key));
                fputc(':', out);
                json_write(out, value->as.object.values[index]);
            }
            fputc('}', out);
            break;
        default:
            fputs("null", out);
            break;
    }
}
