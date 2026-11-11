CC ?= cc
CFLAGS ?= -std=c11 -O2 -Wall -Wextra
LDLIBS ?= -lm

BIN := converter_sandbox
SRC := src/main.c src/harness.c src/user_code.c
HDR := src/harness.h src/user_code.h src/error_prelude.h

$(BIN): $(SRC) $(HDR)
	$(CC) $(CFLAGS) -o $(BIN) $(SRC) $(LDLIBS)

clean:
	rm -f $(BIN)

.PHONY: clean
