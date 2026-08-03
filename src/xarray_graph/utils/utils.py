""" Utility functions for Xarray.
"""

import numpy as np


def index_by_identity(objects: list | tuple, target_obj):
    """
    Returns the index of the first occurrence of target_obj in objects based on identity.
    Returns -1 if the object is not found.
    """
    for i, item in enumerate(objects):
        if item is target_obj:
            return i
    return -1


def unique_name(name: str, names: list[str], unique_counter_start: int = 1) -> str:
    """ Return name_1, or name_2, etc. until a unique name is found that does not exist in names.
    """
    if name not in names:
        return name
    base_name = name
    i = unique_counter_start
    name = f'{base_name}_{i}'
    while name in names:
        i += 1
        name = f'{base_name}_{i}'
    return name


def str_to_value(text: str) -> bool | int | float | str | tuple | list | dict | set | np.ndarray:
    """ Convert a string representation of a value into the corresponding Python object.
    
    Handles basic values and containers and numpy arrays.
    """
    stext = text.strip()
    if stext.lower() == 'true':
        # boolean
        return True
    if stext.lower() == 'false':
        # boolean
        return False
    if stext.startswith('(') and stext.endswith(')'):
        # tuple
        inner_text = stext[1:-1]
        values = [str_to_value(item.strip()) for item in split_text(inner_text)]
        return tuple(values)
    if stext.startswith('[') and stext.endswith(']'):
        # list
        inner_text = stext[1:-1]
        values = [str_to_value(item.strip()) for item in split_text(inner_text)]
        return values
    if stext.startswith('array(') and stext.endswith(')'):
        # numpy array
        inner_text = stext[6:-1]
        values = str_to_value(inner_text)
        return np.array(values)
    if stext.startswith('{') and stext.endswith('}'):# and dtype in [None, 'dict', 'set']:
        # dict or set
        inner_text = stext[1:-1]
        items = split_text(inner_text)
        if not items:
            # empty dict or set (default to dict)
            return {}
        if ':' in items[0]:
            # TODO: This check is not perfect, but it should work for most cases.
            # dict
            values = {}
            for item in items:
                key, value = item.split(':', 1)
                values[key.strip()] = str_to_value(value.strip())
            return values
        else:
            # set
            values = set()
            for item in items:
                values.add(str_to_value(item.strip()))
            return values
    try:
        # first try to convert to int
        value = int(text)
        return value
    except ValueError:
        try:
            # next try to convert to float
            value = float(text)
            return value
        except ValueError:
            # if not a number, return as string
            return text


def value_to_str(value, in_array: bool = False) -> str:
    """ Convert a value to its string representation.

    Handles basic values and containers and numpy arrays (keeps track of array dtype).
    """
    if isinstance(value, tuple):
        return '(' + ', '.join([value_to_str(val) for val in value]) + ')'
    if isinstance(value, list):
        return '[' + ', '.join([value_to_str(val) for val in value]) + ']'
    if isinstance(value, dict):
        return '{' + ', '.join([f'{key}: ' + value_to_str(val) for key, val in value.items()]) + '}'
    if isinstance(value, set):
        return '{' + ', '.join([value_to_str(val) for val in value]) + '}'
    if isinstance(value, np.ndarray):
        text = '[' + ', '.join([value_to_str(val, in_array=True) for val in value]) + ']'
        if not in_array:
            return f'array({text})'
        return text
    return str(value)


def split_text(text: str) -> list[str]:
    parts: list[str] = ['']
    grouping: str = ''
    for char in text:
        if char == '(' or char == '[' or char == '{':
            grouping += char
        elif grouping:
            if grouping[-1] == '(' and char == ')':
                grouping = grouping[:-1]
            elif grouping[-1] == '[' and char == ']':
                grouping = grouping[:-1]
            elif grouping[-1] == '{' and char == '}':
                grouping = grouping[:-1]
        if char == ',' and not grouping:
            parts.append('')
        else:
            parts[-1] += char
    parts = [part.strip() for part in parts if part.strip()]
    return parts


def test():
    import numpy as np

    # Unfortunately, ast.literal_eval does not support numpy arrays, so we need to implement our own parser.
    # from ast import literal_eval

    # Although asteval can evaluate numpy arrays, I did not find it to be very convenient, so I implemented my own limited parser instead.
    # from asteval import Interpreter
    # aeval = Interpreter()
    # aeval("import numpy as np")

    test_values = [
        True,
        False,
        42,
        3.14,
        (1, 2, 3),
        [1, 2, 3],
        {1, 2, 3},
        {"a": 1, "b": 2, "c": np.array([1, 2, 3]), "d": {"nested": 42}, "e": np.int64(42)},
        np.array([1, 2, 3]),
        np.int64(42),
        np.float64(3.14),
        np.array([[1, 2], [3, 4]]),
        np.array([1, 2, 3], dtype=np.float32),
        np.array([1, 2, 3], dtype=np.int32),
    ]
    values_back = []
    print('-'*82)
    for value in test_values:
        s = value_to_str(value)
        value_back = str_to_value(s)
        print(f'{value} <{type(value).__name__}> -> "{s}" -> {value_back} <{type(value_back).__name__}>')
        values_back.append(value_back)
    
    # print(values_back[7]['c'].dtype)
    # print(type(values_back[7]['e']))


if __name__ == '__main__':
    test()
