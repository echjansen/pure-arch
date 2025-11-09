#!/usr/bin/env bash
set -euo pipefail               # Exit on errors, etc

# -----------------------------------------------------------------------------
# Script: pure-linux-tui.sh
# Description: Terminal print and display functions
# Author: echjansen
# Date: 2025-11-07
# -----------------------------------------------------------------------------

# --- Style Attributes ---
readonly FAINT="\e[2m"
readonly BOLD='\e[1m'
readonly ITALICS="\e[3m"
readonly UNDERLINE='\e[4m'
readonly THROUGHLINE="\e[9m"
readonly INVERT='\e[7m'
readonly FLASHING="\e[5m"
readonly FLASHING2="\e[6m"
readonly INVISIBLE="\e[7m"
readonly RESET='\e[0m'

# ANSI Color Codes
readonly RED='\e[31m'
readonly GREEN='\e[32m'
readonly YELLOW='\e[33m'
readonly BLUE='\e[34m'
readonly WHITE='\e[137m'

# --- 8 Standard Foreground (Text) Colors ---
readonly FG_BLACK='\e[30m'
readonly FG_RED='\e[31m'
readonly FG_GREEN='\e[32m'
readonly FG_YELLOW='\e[33m'
readonly FG_BLUE='\e[34m'
readonly FG_MAGENTA='\e[35m'
readonly FG_CYAN='\e[36m'
readonly FG_WHITE='\e[37m'

# --- 8 Standard Background Colors ---
readonly BG_BLACK='\e[40m'
readonly BG_RED='\e[41m'
readonly BG_GREEN='\e[42m'
readonly BG_YELLOW='\e[43m'
readonly BG_BLUE='\e[44m'
readonly BG_MAGENTA='\e[45m'
readonly BG_CYAN='\e[46m'
readonly BG_WHITE='\e[47m'

# --- 8 Bright/High-Intensity Foreground Colors (16-Color Palette) ---
readonly FG_BRIGHT_BLACK='\e[90m'
readonly FG_BRIGHT_RED='\e[91m'
readonly FG_BRIGHT_GREEN='\e[92m'
readonly FG_BRIGHT_YELLOW='\e[93m'
readonly FG_BRIGHT_BLUE='\e[94m'
readonly FG_BRIGHT_MAGENTA='\e[95m'
readonly FG_BRIGHT_CYAN='\e[96m'
readonly FG_BRIGHT_WHITE='\e[97m'

# --- 8 Bright/High-Intensity Background Colors ---
readonly BG_BRIGHT_BLACK='\e[100m'
readonly BG_BRIGHT_RED='\e[101m'
readonly BG_BRIGHT_GREEN='\e[102m'
readonly BG_BRIGHT_YELLOW='\e[103m'
readonly BG_BRIGHT_BLUE='\e[104m'
readonly BG_BRIGHT_MAGENTA='\e[105m'
readonly BG_BRIGHT_CYAN='\e[106m'
readonly BG_BRIGHT_WHITE='\e[107m'

# Global configuration
SPINNER_PID=""                   # Global to store the PID
readonly SPINNER_CHARS='-/|\'    # Spinner characters
readonly COLOR_SPINNER="$YELLOW" # Default color for the spinner
readonly COLOR_SUCCESS="$BOLD$GREEN"
readonly COLOR_FAILURE="$BOLD$RED"

readonly PREFIX_SUCCESS="[O]"
readonly PREFIX_WARNING="[!]"
readonly PREFIX_FAILURE="[X]"

## Helper Functions
### = tui_get_teminal_width: Set COLUMNS to terminal width
function tui_get_terminal_width() {
    local width_val

    # Use tput for robustness; default to 80 if tput fails
    width_val=$(tput cols 2>/dev/null)

    # Check if the command succeeded and returned a number
    if [[ -z "$width_val" || ! "$width_val" =~ ^[0-9]+$ ]]; then
        COLUMNS=80
    else
        # Set the global COLUMNS variable
        COLUMNS="$width_val"
    fi
}
tui_get_terminal_width

## TUI Print Functions
### tui_print_line:    Print seperator line of provided character.
function tui_print_line() {
    # local ensures variables stay within the function scope
    local color="${1:-$YELLOW}" # 1.: Color code (e.g., $RED, $BLUE)
    local char="${2:-=}"        # 2.: Separator character (defaults to '=')

    # We use the global $RESET defined previously
    local reset_code="$RESET"

    # 1. Start color, if provided
    printf "%b" "$color"

    # 2. Print the full line of the character using the printf/tr trick
    printf "%${COLUMNS}s" | tr ' ' "$char"

    # 3. End with the reset code and a newline
    printf "%b\n" "$reset_code"
}

### tui_print_title:   Print padded centered title
function tui_print_title() {
    local title="$1"            # 1.: The main text content
    local color="${2:-$YELLOW}" # 2.: Color. Default to $YELLOW
    local pad_char="${3:-=}"    # 3.: Padding character.  Default to '='

    local raw_text="${title}"
    local text_len="${#raw_text}"
    local pad_width_total
    local pad_width_left
    local pad_width_right

    # 1. Calculate the total required padding width
    # If the text is longer than the column width, truncate it (safety first)
    if (( text_len >= COLUMNS )); then
        raw_text=$(echo "$raw_text" | cut -c 1-"${COLUMNS}")
        text_len="${#raw_text}"
        pad_width_total=0
    else
        pad_width_total=$((COLUMNS - text_len - 2)) # -2 for the two spaces around the text
    fi

    # 2. Calculate left and right padding
    # integer division for left padding
    pad_width_left=$((pad_width_total / 2))
    # remaining padding goes to the right
    pad_width_right=$((pad_width_total - pad_width_left))

    # 3. Create the left and right padding strings using printf/tr trick
    # Use spaces for padding creation, then tr to replace with pad_char
    local pad_left
    local pad_right

    # If padding is negative, set to 0 (for extremely long titles)
    if (( pad_width_left > 0 )); then
        pad_left=$(printf "%${pad_width_left}s" | tr ' ' "$pad_char")
    fi
    if (( pad_width_right > 0 )); then
        pad_right=$(printf "%${pad_width_right}s" | tr ' ' "$pad_char")
    fi

    # 4. Construct the final line and print
    # The final format is: [Left Pad] [ Space ] [ Text ] [ Space ] [ Right Pad ]
    # Note: We skip the two spaces if the total padding is 0 or less
    if (( pad_width_total > 0 )); then
        printf "%b%s %s %s%b\n" "$color" "$pad_left" "$raw_text" "$pad_right" "$RESET"
    else
        # If no room for padding/spaces, just print the truncated text
        printf "%b%s%b\n" "$color" "$raw_text" "$RESET"
    fi
}

### tui_print_message: Print message text
function tui_print_message() {
    local message="$1"          # 1. The main text content (MUST HAVE)
    local color="${2:-}"        # 2. Color code (optional)
    local prefix="${3:-}"       # 3. Prefix (optional, e.g., "[OK]")
    local postfix="${4:-}"      # 4. Postfix (optional, e.g., "DONE")

    local prefixed_string=""    # Holds [PREFIX] + space (if present)
    local postfix_string=""     # Holds [POSTFIX]
    local truncated_message
    local available_width
    local fill_spaces
    local padding=""

    # --- 1. Prepare Prefixes and Postfixes (including separation spaces) ---

    # Prepend space to the postfix for separation
    if [[ -n "$postfix" ]]; then
        postfix_string=" ${postfix}" # Space before postfix
    fi

    # Append space to the prefix for separation
    if [[ -n "$prefix" ]]; then
        prefixed_string="${prefix} " # Space after prefix
    fi

    # --- 2. Calculate Available Width ---

    local prefix_len=${#prefixed_string}  # Now includes the space if present
    local postfix_len=${#postfix_string}  # Now includes the space if present

    # Available width for the MESSAGE content
    available_width=$(( COLUMNS - prefix_len - postfix_len ))

    # --- 3. Truncate and Calculate Padding ---

    truncated_message=$(echo "$message" | cut -c 1-"${available_width}")

    # Calculate spaces needed to push the postfix to the right edge
    local content_len=$(( ${#prefixed_string} + ${#truncated_message} + ${#postfix_string} ))
    fill_spaces=$(( COLUMNS - content_len ))

    if (( fill_spaces > 0 )); then
        printf -v padding "%*s" "$fill_spaces" ""
    fi

    # --- 4. Print the Final Line ---

    # Structure: [Prefixed String] [Truncated Message] [PADDING] [Postfix String]
    printf "%b%s%s%s%s%b\n" "$color" "$prefixed_string" "$truncated_message" "$padding" "$postfix_string" "$RESET"
}

### tui_print_section: Print a sperated padded section
function tui_print_section() {
    local section_text="$1"     # 1. The main text content
    local color="${2:-$YELLOW}" # 2. Color code (e.g., $RED, $BLUE)
    local char="${3:-=}"        # 3. Separator character (defaults to '=')

    tui_print_title "$section_text" "${BG_GREEN}${FG_BLACK}"
}

### tui_print_banner:  Print three line banner message
function tui_print_banner() {
    local banner_text="$1"        # 1. The main text content
    local color="${2:-$BG_GREEN}" # 2. Color code (e.g., $RED, $BLUE)
    local char="${3:- }"          # 3. Separator character (defaults to '=')

    tui_print_message "" "${color}"
    tui_print_title "$banner_text" "${color}" "$char"
    tui_print_message "" "${color}"
    echo ""
}

### tui_start_spinner: Print message with busy spinner
function tui_start_spinner() {
    local message="$1"
    local spin_chars="$SPINNER_CHARS"
    local delay=0.1
    local i=0
    local char_count=${#spin_chars}

    if [[ -n "$SPINNER_PID" ]]; then
        echo "Error: Spinner already running with PID $SPINNER_PID" >&2
        return 1
    fi

    # Run in a subshell, but redirect stdout/stderr to /dev/tty to ensure
    # the output is directed to the terminal, avoiding potential pipe issues.
    (
        while true; do
            i=$(( (i + 1) % char_count ))
            char="${spin_chars:i:1}"
            prefix="[${char}] " # Added a space here for cleaner look

            # Calculate the space available for the message
            message_space=$((COLUMNS - ${#prefix}))

            # Truncate the message
            truncated_message=$(echo "$message" | cut -c 1-"${message_space}")

            # Calculate required padding spaces to fill the line
            padding_needed=$((COLUMNS - ${#prefix} - ${#truncated_message}))
            spaces=""
            printf -v spaces "%*s" "$padding_needed" ""

            # Print the line: \r is BEFORE the content to clear the previous line
            printf "\r%b%s%s%s%b" "$COLOR_SPINNER" "$prefix" "$truncated_message" "$spaces" "$RESET"

            sleep "$delay"
        done
    ) >/dev/tty 2>&1 & # CRITICAL: Redirecting I/O to the terminal device

    SPINNER_PID=$!
    disown
}

### tui_stop_spinner:  Print message overwriting the busy spinner
function tui_stop_spinner() {
    local exit_code="$1"
    local message="$2"
    local final_prefix
    local final_color

    # Stop the background spinner and wait
    if [[ -n "$SPINNER_PID" ]]; then
        kill "$SPINNER_PID" 2>/dev/null

        local timeout=10
        for (( i=0; i<timeout; i++ )); do
            if kill -0 "$SPINNER_PID" 2>/dev/null; then
                sleep 0.1
            else
                break
            fi
        done
        # Force kill if needed
        if kill -0 "$SPINNER_PID" 2>/dev/null; then
            kill -9 "$SPINNER_PID" 2>/dev/null
        fi

        SPINNER_PID=""
    fi

    # Determine and Print the final status
    if [[ "$exit_code" -eq 0 ]]; then
        final_prefix="$PREFIX_SUCCESS " # Added space
        final_color="$COLOR_SUCCESS"
    else
        final_prefix="$PREFIX_FAILURE " # Added space
        final_color="$COLOR_FAILURE"
    fi

    # Calculate the space available for the message
    local message_space=$((COLUMNS - ${#final_prefix}))

    # Truncate the message
    local final_message
    final_message=$(echo "$message" | cut -c 1-"${message_space}")

    # Calculate required padding spaces to fill the line
    local padding_needed=$((COLUMNS - ${#final_prefix} - ${#final_message}))
    local spaces
    printf -v spaces "%*s" "$padding_needed" ""

    # Print the final line: \r resets cursor, prints content + padding, \n moves to next line
    printf "\r%b%s%s%s%b\n" "$final_color" "$final_prefix" "$final_message" "$spaces" "$RESET"
}

## TUI Input Functions
### = tui_input_prompt
function tui_input_prompt() {
    # The message is printed using '-n -e' to allow escape codes
    # and to keep the cursor on the same line (no automatic newline).
    echo -n -e "${BOLD}${YELLOW}$1 ${RESET}" >&2
}

### = tui_input_choice: Input for user choice
# Function: tui_input_choice
# Description: Prompts the user for input with color, validates against a list of choices, and returns the chosen value.
# Usage: tui_input_choice "Your Prompt Message (e.g., [Y/n])" "Y,y,N,n" [OPTIONAL_PROMPT_COLOR_CODE]
#
# Arguments:
#   $1 - The prompt message to display to the user.
#   $2 - A comma-separated string of valid choices (e.g., "yes,no,y,n").
#   $3 - (Optional) The ANSI color code for the prompt text (default: $CYAN).
#
# Returns:
#   The validated user input is echoed to standard output.
#   Returns 0 on success, 1 on invalid usage or interrupt.
tui_input_choice() {
    # 1. Use 'local' for all variables to prevent clobbering global scope
    local prompt_msg="$1"
    local valid_choices_str="$2"
    local prompt_color="${3:-$BG_YELLOW}"

    local user_input
    local choice_found=0

    # Check for required arguments
    if [[ -z "$prompt_msg" || -z "$valid_choices_str" ]]; then
        echo -e "${RED}ERROR:${RESET} Usage: tui_input_choice <prompt_message> <comma_separated_choices> [prompt_color]" >&2
        return 1
    fi

    # Convert the comma-separated string of choices into an array for easier checking
    # Uses bash parameter expansion to replace commas with spaces for 'read'
    local -a valid_choices=($(echo "${valid_choices_str//,/ }"))

    # 2. Main loop for continuous prompting until valid input is received
    while [[ "$choice_found" -eq 0 ]]; do
        # Display the color-coded prompt and read the input
        # -r prevents backslash escapes from being interpreted
        # -p allows specifying a prompt
        #echo -e "$prompt_color$prompt_msg $RESET"
        tui_input_prompt ${prompt_msg}
        read -r user_input

        # 3. Check for successful read (e.g., not interrupted by Ctrl+C)
        if [[ $? -ne 0 ]]; then
            echo -e "\n${RED}Input operation cancelled.${RESET}" >&2
            return 1
        fi

        # Trim leading/trailing whitespace from input
        user_input="$(echo -e "${user_input}" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"

        # Check if the input is one of the valid choices
        for choice in "${valid_choices[@]}"; do
            if [[ "$user_input" == "$choice" ]]; then
                choice_found=1
                break
            fi
        done

        # 4. Display error message if the input was invalid
        if [[ "$choice_found" -eq 0 ]]; then
            # The error message also uses a specific color (LIGHT_RED)
            echo -e "${RED}Invalid input. Please choose from: ${valid_choices_str}${RESET}" >&2
        fi
    done

    # The output is echoed, which is the standard way functions return values in shell scripting
    return 0
}
