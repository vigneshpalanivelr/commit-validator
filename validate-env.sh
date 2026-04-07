#!/bin/bash
# Validate mrproper.env file format for Docker --env-file compatibility

ENV_FILE="${1:-mrproper.env}"

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: File not found: $ENV_FILE"
    echo "Usage: $0 [env-file-path]"
    exit 1
fi

echo "========================================="
echo "Validating: $ENV_FILE"
echo "========================================="
echo ""

# Check for leading whitespace
echo "[1] Checking for leading whitespace..."
LEADING_SPACE_LINES=$(grep -n '^[[:space:]]' "$ENV_FILE" | grep -v '^[[:space:]]*#' | grep -v '^[[:space:]]*$')
if [ -n "$LEADING_SPACE_LINES" ]; then
    echo "    ✗ FAIL: Found lines with leading whitespace (not compatible with Docker --env-file):"
    echo "$LEADING_SPACE_LINES" | head -10
    echo ""
    echo "    Fix: Remove leading spaces/tabs from variable assignments"
    ISSUES=1
else
    echo "    ✓ PASS: No leading whitespace found"
fi

# Check for BFA_HOST
echo ""
echo "[2] Checking for BFA_HOST variable..."
BFA_HOST_LINE=$(grep -n '^BFA_HOST=' "$ENV_FILE")
if [ -n "$BFA_HOST_LINE" ]; then
    echo "    ✓ PASS: BFA_HOST found:"
    echo "    $BFA_HOST_LINE"

    # Check if it's set to a value
    BFA_VALUE=$(grep '^BFA_HOST=' "$ENV_FILE" | cut -d= -f2)
    if [ -z "$BFA_VALUE" ]; then
        echo "    ⚠ WARNING: BFA_HOST is set but empty"
    fi
else
    echo "    ⚠ WARNING: BFA_HOST not found or commented out"
    echo "    Note: Without BFA_HOST, system will use legacy AI_SERVICE_URL mode"
fi

# Check for required variables
echo ""
echo "[3] Checking required variables..."
REQUIRED_VARS=("GITLAB_ACCESS_TOKEN" "API_TIMEOUT" "LOG_DIR" "LOG_LEVEL")
for VAR in "${REQUIRED_VARS[@]}"; do
    if grep -q "^${VAR}=" "$ENV_FILE"; then
        VALUE=$(grep "^${VAR}=" "$ENV_FILE" | cut -d= -f2)
        if [ -n "$VALUE" ]; then
            echo "    ✓ $VAR is set"
        else
            echo "    ✗ $VAR is set but empty"
            ISSUES=1
        fi
    else
        echo "    ✗ $VAR not found"
        ISSUES=1
    fi
done

# Show what Docker will see
echo ""
echo "[4] Preview: Variables Docker will load:"
echo "==========================================="
grep -v '^#' "$ENV_FILE" | grep -v '^[[:space:]]*$' | grep '=' | while read -r line; do
    # Check if line has leading whitespace
    if [[ "$line" =~ ^[[:space:]] ]]; then
        echo "    ✗ IGNORED (leading space): $line"
    else
        VAR_NAME=$(echo "$line" | cut -d= -f1)
        VAR_VALUE=$(echo "$line" | cut -d= -f2-)
        # Mask sensitive values
        if [[ "$VAR_NAME" == "GITLAB_ACCESS_TOKEN" ]]; then
            echo "    ✓ $VAR_NAME=${VAR_VALUE:0:15}..."
        elif [[ "$VAR_NAME" == "BFA_TOKEN_KEY" ]]; then
            echo "    ✓ $VAR_NAME=${VAR_VALUE:0:20}..."
        else
            echo "    ✓ $line"
        fi
    fi
done
echo "==========================================="

echo ""
if [ -n "$ISSUES" ]; then
    echo "Result: VALIDATION FAILED - Fix issues above"
    exit 1
else
    echo "Result: VALIDATION PASSED - File format is correct"
    exit 0
fi
