def formatColor(text, color: str = "reset"):
    reset = "\033[0;m"

    if color == "bold_red":
        return "\033[;31m" + str(text) + reset
    if color == "gray":
        gray = "\033[;90m"
        return gray + str(text) + reset
    if color == "green":
        green = "\033[;32m"
        return green + str(text) + reset
    if color == "grey":
        grey = "\033[;90m"
        return grey + str(text) + reset
    if color == "red":
        red = "\033[1;31m"
        return red + str(text) + reset
    if color == "reset":
        return reset + str(text) + reset
    if color == "yellow":
        yellow = "\033[;33m"
        return yellow + str(text) + reset
    return "Invalid Color: Please use either:\n• grey/gray\n• yellow\n• red\n• bold_red\n• green\n• reset (resets color back to white)"
