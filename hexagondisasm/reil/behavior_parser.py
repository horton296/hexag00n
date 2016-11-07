from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

from builtins import (ascii, bytes, chr, dict, filter, hex, input,
                      int, map, next, oct, open, pow, range, round,
                      str, super, zip)

import os
import re
import sys
import logging
import ply.lex as lex
import ply.yacc as yacc

from hexagondisasm import common
from hexagondisasm.common import UnknownBehaviorException, UnexpectedException

# BARF imports
from barf.arch.translator import TranslationBuilder
from barf.core.reil.reil import ReilRegisterOperand, ReilImmediateOperand
from barf.utils.utils import VariableNamer
# from barf.core.reil import ReilMnemonic


hexagon_size = 32
# TODO: Where to define this?


_ir_name_generator = VariableNamer("t", separator="")
# TODO: Used by the HexagonTranslationBuilder, is kept as a global variable for now,
# later it should be added to the HexagonTranslator (like BARF).

logging.basicConfig(
    level=logging.DEBUG,
    stream=sys.stdout,
    format="%(filename)10s:%(lineno)4d: %(message)s"
)
log = logging.getLogger()
# TODO: Add the logger to the HexagonBehaviorParser class?


class Parser(object):
    """Base class for a lexer/parser that has the rules defined as methods.

    Adapted from a `PLY example`_.

    .. _PLY example: https://github.com/dabeaz/ply/blob/master/example/newclasscalc/calc.py

    """
    tokens = ()
    precedence = ()

    def __init__(self, **kw):
        self.debug = kw.get('debug', 0)
        self.names = {}
        try:
            modname = os.path.split(os.path.splitext(__file__)[0])[1] + "_" + self.__class__.__name__
        except:
            modname = "parser" + "_" + self.__class__.__name__
        self.tabmodule = modname + "_" + "parsetab"
        self.debugfile = modname + ".dbg"

        # Build the lexer and parser
        lex.lex(module=self, debug=False, debuglog=log)
        yacc.yacc(module=self,
                  debug=self.debug,
                  debugfile=self.debugfile,
                  tabmodule=self.tabmodule)

    def parse(self, input):
        """Parse input text with rules defined in the child class
        (`HexagonBehaviorParser`).

        Args:
            input (str): Input text to parse.

        Returns:
            List[ReilInstruction]: Equivalent REIL instructions.

        Raises:
            UnknownBehaviorException: If the rules define can't process the input text.

        TODOs:
            * Define return type.

            * Decouple base and child classes, or document it appropriately.

            * Return the instruction lists of the TranslationBuilder object, not the object itself.

        """
        # return yacc.parse(input, debug=self.debug)

        return yacc.parse(input, debug = log if self.debug else False)


class HexagonBehaviorParser(Parser):
    """Parser for the Hexagon instructions behavior.

    It contains the rules for both the lexer and parser.

   """
    def __init__(self, **kw):
        super(HexagonBehaviorParser, self).__init__(**kw)

    # Lexer rules.
    # ------------

    reserved = {
        'if' : 'IF',
        'else' : 'ELSE',
    }

    tokens = [
         'REG', 'IMM', 'NAME', 'IMM_OP', 'MEM_ACCESS', 'REG_EA',

         # Literals (identifier, integer constant, float constant, string constant, char const)
         'ID', 'TYPEID', 'ICONST', 'FCONST', 'SCONST', 'CCONST',

         # Operators (+,-,*,/,%,|,&,~,^,<<,>>, ||, &&, !, <, <=, >, >=, ==, !=)
         'PLUS', 'MINUS', 'TIMES', 'DIVIDE', 'MOD',
         'OR', 'AND', 'NOT', 'XOR', 'LSHIFT', 'RSHIFT',
         'LOR', 'LAND', 'LOG_NOT',
         'LT', 'LE', 'GT', 'GE', 'EQ', 'NE',

         # Assignment (=, *=, /=, %=, +=, -=, <<=, >>=, &=, ^=, |=)
         'EQUALS', 'TIMESEQUAL', 'DIVEQUAL', 'MODEQUAL', 'PLUSEQUAL', 'MINUSEQUAL',
         'LSHIFTEQUAL', 'RSHIFTEQUAL', 'ANDEQUAL', 'XOREQUAL', 'OREQUAL',

         # Increment/decrement (++,--)
         'PLUSPLUS', 'MINUSMINUS',

         # Structure dereference (->)
         'ARROW',

         # Conditional operator (?)
         'CONDOP',

         # Delimeters ( ) [ ] { } , . ; :
         'LPAREN', 'RPAREN',
         'LBRACKET', 'RBRACKET',
         'LBRACE', 'RBRACE',
         'COMMA', 'PERIOD', 'SEMI', 'COLON',

         # Ellipsis (...)
         'ELLIPSIS',

         # Extract bit prom pred reg: "Pu[0]"
         'BIT_EXTRACTOR'

     ] + list(reserved.values())

    # Completely ignored characters
    t_ignore = ' \t\x0c'

    # Operators
    t_PLUS = r'\+'
    t_MINUS = r'-'
    t_TIMES = r'\*'
    t_DIVIDE = r'/'
    t_OR = r'\|'
    t_AND = r'&'
    t_NOT = r'!'
    t_XOR = r'\^'
    t_LOG_NOT = r'~'
    t_LSHIFT = r'<<'
    t_RSHIFT = r'>>'
    t_LT = r'<'
    t_GT = r'>'
    t_LE = r'<='
    t_GE = r'>='
    t_EQ = r'=='
    t_NE = r'!='

    # Assignment operators
    t_EQUALS = r'='
    t_TIMESEQUAL = r'\*='
    t_DIVEQUAL = r'/='
    t_PLUSEQUAL = r'\+='
    t_MINUSEQUAL = r'-='
    t_LSHIFTEQUAL = r'<<='
    t_RSHIFTEQUAL = r'>>='
    t_ANDEQUAL = r'&='
    t_OREQUAL = r'\|='
    t_XOREQUAL = r'\^='

    # Increment/decrement
    t_PLUSPLUS = r'\+\+'
    t_MINUSMINUS = r'--'

    # Conditional operator
    t_CONDOP = r'\?'

    # Delimeters
    t_LPAREN = r'\('
    t_RPAREN = r'\)'
    t_LBRACE = r'\{'
    t_RBRACE = r'\}'
    t_COMMA = r','
    t_PERIOD = r'\.'
    t_SEMI = r';'
    t_COLON = r':'

    def t_newline(self, t):
        r'\n+'
        t.lexer.lineno += t.value.count("\n")

    def t_error(self, t):
        raise UnknownBehaviorException("Illegal character {:s} in: {:s}".format(t.value[0], t.value))

    # TODO: Rethink how to handle EA.
    def t_MEM_ACCESS(self, t):
        r'\*EA'
        t.value = 'EA'
        return t
    def t_REG_EA(self, t):
        r'EA'
        return t

    # TODO: Wait to use this definition until necessary.
    # def t_NAME(self, t):
    #     r'[a-zA-Z_][a-zA-Z0-9_]*'
    #     t.type = HexagonBehaviorParser.reserved.get(t.value, 'NAME')    # Check for reserved words
    #     return t

    def t_REG(self, t):
        r'[RPNMC]\w{1,2}(\.new)?'
        # TODO: this is taken from the decoder, should be unified.
        return t

    def t_IMM(self, t):
        r'(0x)?[a-fA-F0-9]+'
        t.value = re.sub('0x', '', t.value)
        t.value = int(t.value, 16)
        # TODO: Is it always hexadecimal format?
        return t

    # Parser rules.
    # ------------

    precedence = (
        # ('nonassoc', 'SEMI'),
        # ('nonassoc','TIMESEQUAL','DIVEQUAL','PLUSEQUAL','MINUSEQUAL','LSHIFTEQUAL','RSHIFTEQUAL','ANDEQUAL','OREQUAL','XOREQUAL'),
        # ('nonassoc', 'NOT', 'OR', 'AND', 'XOR'),
        # ('nonassoc', 'EQ', 'NE',),
        # ('nonassoc', 'LT', 'GT', 'LE', 'GE',),
        # ('left','PLUS','MINUS'),
        # ('left','TIMES','DIVIDE'),
        # ('right', 'UNARY_OPERATOR'),
        # ('left', 'UNARY_OPERATOR_LEFT'),
        # ('nonassoc', 'LPAREN', 'RPAREN', 'LBRACE', 'RBRACE'),
    )

    def p_statement_expr(self, p):
        'statement : expression'
        p[0] = p[1]
        print_debug("Expression {:s} to Statement {:s}".format(p[1], p[0]))
        # TODO: Set expression value to None when converting it to a statement.

    def p_statemenlist(self, p):
        "statement : statement SEMI statement"
        p[1].extend_instructions(p[3])
        p[0] = p[1]
        print_debug("join statements")

    def p_statement_list_2(self, p):
        "statement : statement SEMI"
        p[0] = p[1]

    def p_statement_statementassign(self, p):
        '''statement : statement_assign'''
        p[0] = p[1]

    def p_expression_register(self, p):
        "expression : register"
        p[0] = p[1]

    def p_register_reg(self, p):
        "register : REG"
        p[0] = HexagonTranslationBuilder(_ir_name_generator)
        p[0].set_value(ReilRegisterOperand(p[1], hexagon_size))
        print_debug("Create REIL register: {:s}".format(p[1]))

    def p_statementassign(self, p):
        '''statement_assign : register EQUALS        expression
                            | register TIMESEQUAL    expression
                            | register DIVEQUAL      expression
                            | register PLUSEQUAL     expression
                            | register MINUSEQUAL    expression
                            | register LSHIFTEQUAL   expression
                            | register RSHIFTEQUAL   expression
                            | register ANDEQUAL      expression
                            | register OREQUAL       expression
                            | register XOREQUAL       expression'''

        p[3].add(p[3]._builder.gen_str(p[3].get_value(), p[1].get_value()))
        p[3].set_value(p[1])
        p[0] = p[3]
        print_debug("assign {:s} -> {:s}".format(p[3].get_value(), p[1].get_value()))

    def p_expression_binop(self, p):
        '''expression : expression PLUS expression
                      | expression MINUS expression
                      | expression TIMES expression
                      | expression DIVIDE expression
                      | expression OR expression
                      | expression AND expression
                      | expression NOT expression
                      | expression XOR expression
                      | expression LOG_NOT expression
                      | expression LSHIFT expression
                      | expression RSHIFT expression
                      | expression LT expression
                      | expression GT expression
                      | expression LE expression
                      | expression GE expression
                      | expression EQ expression
                      | expression NE expression'''
        #     if p[2] == '+'  : p[0] = p[1] + p[3]
        #     elif p[2] == '-': p[0] = p[1] - p[3]
        #     elif p[2] == '*': p[0] = p[1] * p[3]
        #     elif p[2] == '/': p[0] = p[1] / p[3]
        p[1].extend_instructions(p[3])
        binop_dst = p[1].temporal(hexagon_size)
        p[1].add(p[1]._builder.gen_add(p[1].get_value(), p[3].get_value(), binop_dst))
        p[1].set_value(binop_dst)
        p[0] = p[1]
        inst = "binop {:s} {:s} {:s}".format(p[1].get_value(), p[2], p[3].get_value())
        print_debug(inst)

    def p_error(self, p):
        if p:
            error_msg = "Syntax error at {:s}".format(str(p.value))
        else:
            error_msg = "Syntax error at EOF"
        raise UnknownBehaviorException(error_msg)


class HexagonTranslationBuilder(TranslationBuilder):
    """Translation builder for the Hexagon parser.

    Used to hold instructions (through TranslationBuilder's `_instructions`)
    and to hold the expression value (``_value``).

    Attributes:
        _value (Optional[ReilOperand]): Value of the expression that the REIL
            `_instructions` list represent, or None if they are represent a
            statement.

    """
    # __slots__ = ['']
    # TODO: Add slots.

    def __init__(self, ir_name_generator):
        super(HexagonTranslationBuilder, self).__init__(ir_name_generator, 'Hexagon')
        # TODO: Define architecture_mode as 'Hexagon' in BARF.

        self._value = None

    def get_instructions(self):
        return self._instructions

    def extend_instructions(self, tb):
        """Extend the REIL instructions list contained in this object.

        Args:
            tb (HexagonTranslationBuilder): The list of REIL
                instructions it contains will be the source of the extension.

        Returns:
            None: the extension is applied to the instructions list itself.

        """
        self._instructions.extend(tb._instructions)

    # TODO: Use proper setters/getters.
    def set_value(self, value):
        self._value = value

    def get_value(self):
        if self._value is None:
            raise UnexpectedException()
        return self._value


def print_debug(s):
    log.debug(s)
    return


if __name__ == "__main__":

    parser = HexagonBehaviorParser(debug = True)

    inst_defs = common.pickle_load(common.INST_DEF_PATH)

    for inst in inst_defs:
        behavior = inst.behavior

        # TODO: Temporal hack to parse particular behaviors
        if "Rd=Rs+Rt;" not in inst.behavior: continue

        if inst.behavior == '':
            # No behavior available (probably it wasn't correctly parsed
            # from the Hexagon Reference Manual).
            continue

        try:
            print_debug("Parsing: {:s}".format(inst.behavior.strip()))
            parsed = parser.parse(behavior)
            for ri in parsed._instructions:
                print(ri)
            print_debug("DONE!")
        except UnknownBehaviorException as e:
            # log.info("Unknown behavior instruction: {:s}".format(behavior))
            pass
