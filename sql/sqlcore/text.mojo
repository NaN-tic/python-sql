"""Identifier quoting and alias naming."""


def quote_identifier(value: String) -> String:
    var result = String('"')
    if value.find('"') < 0:
        result += value
        result += '"'
        return result
    for codepoint in value.codepoint_slices():
        var character = String(codepoint)
        if character == '"':
            result += '""'
        else:
            result += character
    result += '"'
    return result


def quote_qualified(alias_value: String, column_name: String) -> String:
    if column_name == "*":
        return quote_identifier(alias_value) + ".*"
    return quote_identifier(alias_value) + "." + quote_identifier(column_name)


def qualified_table(name: String, schema: String, database: String) -> String:
    var result = String("")
    if database != "":
        result += quote_identifier(database)
        result += "."
    if schema != "":
        result += quote_identifier(schema)
        result += "."
    result += quote_identifier(name)
    return result


def alias_name(index: Int) -> String:
    comptime letters: String = "abcdefghijklmnopqrstuvwxyz"
    var value = index
    var result = String("")
    while True:
        result = String(letters[byte = value % 26]) + result
        value = value // 26
        if value == 0:
            break
    return result
