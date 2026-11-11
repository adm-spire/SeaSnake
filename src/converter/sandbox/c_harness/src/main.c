/*
 * Fixed runner for differential testing.
 *
 * Reads a JSON array of cases, calls `dispatch` for each one, and writes a JSON
 * array of outcomes. This file is never authored by the LLM.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "harness.h"
#include "user_code.h"

static char *read_file(const char *path) {
    FILE *file = fopen(path, "rb");
    if (file == NULL) {
        return NULL;
    }
    if (fseek(file, 0, SEEK_END) != 0) {
        fclose(file);
        return NULL;
    }
    long size = ftell(file);
    if (size < 0) {
        fclose(file);
        return NULL;
    }
    rewind(file);

    char *buffer = malloc((size_t)size + 1);
    if (buffer == NULL) {
        fclose(file);
        return NULL;
    }
    size_t read = fread(buffer, 1, (size_t)size, file);
    buffer[read] = '\0';
    fclose(file);
    return buffer;
}

int main(int argc, char **argv) {
    if (argc < 3) {
        fputs("usage: converter_sandbox <cases.json> <results.json>\n", stderr);
        return 2;
    }

    char *text = read_file(argv[1]);
    if (text == NULL) {
        fprintf(stderr, "could not read cases: %s\n", argv[1]);
        return 2;
    }

    JsonValue *root = json_parse(text);
    free(text);
    if (root == NULL || value_kind(root) != JSON_ARRAY) {
        fputs("could not parse cases: expected a JSON array\n", stderr);
        return 2;
    }

    JsonValue *rows = value_array();
    size_t count = value_length(root);
    for (size_t index = 0; index < count; index++) {
        JsonValue *item = value_index(root, index);
        if (item == NULL || value_kind(item) != JSON_OBJECT) {
            continue;
        }

        const char *test_id = value_as_string(object_get(item, "test_id"));
        const char *function = value_as_string(object_get(item, "function"));

        Case case_value;
        case_value.test_id = test_id == NULL ? "" : test_id;
        case_value.function = function == NULL ? "" : function;
        case_value.args = object_get(item, "args");
        case_value.kwargs = object_get(item, "kwargs");

        ConvResult result = dispatch(&case_value);

        JsonValue *row = value_object();
        object_set(row, "test_id", value_string(case_value.test_id));
        if (result.ok) {
            object_set(row, "kind", value_string("value"));
            object_set(row, "value",
                       result.value == NULL ? value_null() : result.value);
        } else {
            object_set(row, "kind", value_string("error"));
            object_set(row, "error_variant",
                       value_string(conv_error_variant(result.error.kind)));
            object_set(row, "message", value_string(result.error.message));
            if (result.error.python_type[0] != '\0') {
                object_set(row, "python_type",
                           value_string(result.error.python_type));
            }
        }
        array_push(rows, row);
    }

    FILE *output = fopen(argv[2], "wb");
    if (output == NULL) {
        fprintf(stderr, "could not write results: %s\n", argv[2]);
        return 2;
    }
    json_write(output, rows);
    fputc('\n', output);
    fclose(output);
    return 0;
}
