#include <ctype.h>
#include <errno.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { char *name; char *text; double number; int numeric; } Variable;
typedef struct { unsigned char opcode; size_t count; char **operands; } Instruction;

static char *duplicate(const char *text) {
    size_t length = strlen(text) + 1;
    char *copy = malloc(length);
    if (copy) memcpy(copy, text, length);
    return copy;
}

static void release_instructions(Instruction *instructions, size_t count) {
    for (size_t index = 0; index < count; index++) {
        for (size_t argument = 0; argument < instructions[index].count; argument++) free(instructions[index].operands[argument]);
        free(instructions[index].operands);
    }
    free(instructions);
}

static int read_instructions(const unsigned char *data, size_t length, Instruction **result, size_t *result_count) {
    if (length < 4 || memcmp(data, "VK01", 4)) { fprintf(stderr, "Invalid Vektkove bytecode.\n"); return 0; }
    size_t position = 4, count = 0;
    Instruction *instructions = NULL;
    while (position < length) {
        if (length - position < 2) goto invalid;
        Instruction next = {data[position], data[position + 1], NULL};
        position += 2;
        next.operands = calloc(next.count ? next.count : 1, sizeof(char *));
        if (!next.operands) goto invalid;
        Instruction *grown = realloc(instructions, (count + 1) * sizeof(*instructions));
        if (!grown) { free(next.operands); goto invalid; }
        instructions = grown;
        instructions[count++] = next;
        for (size_t index = 0; index < next.count; index++) {
            if (length - position < 4) goto invalid;
            uint32_t size = ((uint32_t)data[position] << 24) | ((uint32_t)data[position + 1] << 16) | ((uint32_t)data[position + 2] << 8) | data[position + 3];
            position += 4;
            if (size > length - position || memchr(data + position, 0, size)) goto invalid;
            char *operand = malloc((size_t)size + 1);
            if (!operand) goto invalid;
            memcpy(operand, data + position, size);
            operand[size] = '\0';
            instructions[count - 1].operands[index] = operand;
            position += size;
        }
    }
    *result = instructions;
    *result_count = count;
    return 1;
invalid:
    fprintf(stderr, "Invalid or truncated bytecode.\n");
    release_instructions(instructions, count);
    return 0;
}

static Variable *find_variable(Variable *variables, size_t count, const char *name) {
    for (size_t index = 0; index < count; index++) if (!strcmp(variables[index].name, name)) return &variables[index];
    return NULL;
}

static int resolve(const char *token, Variable *variables, size_t count, Variable *value) {
    memset(value, 0, sizeof(*value));
    if (token[0] == '$') {
        Variable *found = find_variable(variables, count, token + 1);
        if (!found) { fprintf(stderr, "Unknown variable %s.\n", token); return 0; }
        value->numeric = found->numeric;
        value->number = found->number;
        value->text = found->text ? duplicate(found->text) : NULL;
        return value->numeric || value->text != NULL;
    }
    if (token[0] == '"') {
        size_t length = strlen(token);
        if (length < 2 || token[length - 1] != '"') { fprintf(stderr, "Invalid quoted string.\n"); return 0; }
        value->text = malloc(length);
        if (!value->text) return 0;
        size_t destination = 0;
        for (size_t index = 1; index < length - 1; index++) {
            char character = token[index];
            if (character == '\\') {
                if (++index >= length - 1) { free(value->text); value->text = NULL; return 0; }
                character = token[index];
                if (character == 'n') character = '\n';
                else if (character == 'r') character = '\r';
                else if (character == 't') character = '\t';
                else if (character != '\\' && character != '"' && character != '/') { fprintf(stderr, "Unsupported string escape.\n"); free(value->text); value->text = NULL; return 0; }
            }
            value->text[destination++] = character;
        }
        value->text[destination] = '\0';
        return 1;
    }
    char *end = NULL;
    errno = 0;
    double number = strtod(token, &end);
    if (end != token && *end == '\0' && errno != ERANGE && isfinite(number)) { value->numeric = 1; value->number = number; return 1; }
    value->text = duplicate(token);
    return value->text != NULL;
}

static int run(const unsigned char *data, size_t length) {
    Instruction *instructions = NULL;
    size_t instruction_count = 0, variable_count = 0;
    Variable *variables = NULL;
    int result = 1;
    if (!read_instructions(data, length, &instructions, &instruction_count)) return 1;
    for (size_t index = 0; index < instruction_count; index++) {
        Instruction instruction = instructions[index];
        size_t expected = instruction.opcode == 28 ? 1 : instruction.opcode == 29 ? 0 : instruction.opcode >= 1 && instruction.opcode <= 3 ? 2 : SIZE_MAX;
        if (instruction.count != expected) { fprintf(stderr, "Unsupported or invalid instruction %u.\n", instruction.opcode); goto finish; }
        if (instruction.opcode == 29) break;
        Variable value;
        if (!resolve(instruction.operands[instruction.opcode == 28 ? 0 : 1], variables, variable_count, &value)) goto finish;
        if (instruction.opcode == 28) {
            if (value.numeric) printf("%.15g\n", value.number);
            else printf("%s\n", value.text);
            free(value.text);
            continue;
        }
        Variable *target = find_variable(variables, variable_count, instruction.operands[0]);
        if (instruction.opcode == 3) {
            if (!target || !target->numeric || !value.numeric) { fprintf(stderr, "add requires numeric values.\n"); free(value.text); goto finish; }
            target->number += value.number;
            free(value.text);
            if (!isfinite(target->number)) { fprintf(stderr, "The result is not a finite number.\n"); goto finish; }
            continue;
        }
        if (!target) {
            Variable *grown = realloc(variables, (variable_count + 1) * sizeof(*variables));
            if (!grown) { free(value.text); goto finish; }
            variables = grown;
            target = &variables[variable_count++];
            memset(target, 0, sizeof(*target));
            target->name = duplicate(instruction.operands[0]);
            if (!target->name) { free(value.text); goto finish; }
        }
        free(target->text);
        target->text = value.text;
        target->numeric = value.numeric;
        target->number = value.number;
        if (instruction.opcode == 1 && target->numeric) {
            char buffer[64];
            snprintf(buffer, sizeof(buffer), "%.15g", target->number);
            target->text = duplicate(buffer);
            target->numeric = 0;
            if (!target->text) goto finish;
        }
    }
    result = 0;
finish:
    for (size_t index = 0; index < variable_count; index++) { free(variables[index].name); free(variables[index].text); }
    free(variables);
    release_instructions(instructions, instruction_count);
    return result;
}

int main(int argc, char **argv) {
    if (argc != 3 || strcmp(argv[1], "run")) { fprintf(stderr, "Usage: vk-portable run program.vkb\n"); return 1; }
    FILE *file = fopen(argv[2], "rb");
    if (!file) { perror(argv[2]); return 1; }
    if (fseek(file, 0, SEEK_END) || ftell(file) < 0) { fclose(file); return 1; }
    long file_size = ftell(file);
    if (fseek(file, 0, SEEK_SET) || (unsigned long)file_size > 64UL * 1024UL * 1024UL) { fclose(file); return 1; }
    unsigned char *data = malloc((size_t)file_size + 1);
    if (!data) { fclose(file); return 1; }
    if (fread(data, 1, (size_t)file_size, file) != (size_t)file_size) { free(data); fclose(file); return 1; }
    fclose(file);
    int result = run(data, (size_t)file_size);
    free(data);
    return result;
}