# SPDX-FileCopyrightText: © 2025 Tenstorrent AI ULC
# SPDX-License-Identifier: Apache-2.0

# Makefile for building the setuid runner binary

CC = gcc
CFLAGS = -Wall -Wextra -O2 -std=c99
TARGET = setuid_runner
SOURCE = setuid_runner.c

# Default target
all: $(TARGET)

# Build the setuid binary
$(TARGET): $(SOURCE)
	$(CC) $(CFLAGS) -o $(TARGET) $(SOURCE)
	@echo "Binary compiled successfully."
	@echo "To set up the setuid permissions, run as root:"
	@echo "  sudo chown root:root $(TARGET)"
	@echo "  sudo chmod 4755 $(TARGET)"
	@echo ""
	@echo "SECURITY WARNING: This will create a setuid root binary."
	@echo "Make sure you understand the security implications."

# Install target (must be run as root)
install: $(TARGET)
	@if [ "$$(id -u)" -ne 0 ]; then \
		echo "Error: install target must be run as root"; \
		exit 1; \
	fi
	chown root:root $(TARGET)
	chmod 4755 $(TARGET)
	@echo "Setuid permissions set successfully."

# Clean target
clean:
	rm -f $(TARGET)

# Test target to verify the binary works
test: $(TARGET)
	@echo "Testing setuid_runner with invalid arguments..."
	@./$(TARGET) || echo "Expected failure - OK"
	@echo "Testing with valid user but invalid command..."
	@./$(TARGET) $$(whoami) invalid_command || echo "Expected failure - OK"
	@echo "Basic tests completed. Manual testing with LSF commands required."

.PHONY: all install clean test
