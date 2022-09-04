from functools import partial
import logging
from typing import List
from datasets import Dataset
import pandas as pd
import numpy as np
from collections import defaultdict
import re
from tqdm import trange
import torch.nn
from . import data_utils

"""Note: all templates should be "stackable" so that they work in the multi-shot setting.
Nothing will be added between them (so probably should end with 2 newlines).
Don't change the order of these (higher should be better).
"""

PROMPT_TEMPLATE_TWO_NUMS = [
    lambda num1, num2, g: (
        f'Given the input numbers {num1} and {num2}, the answer is', f' {g([num1, num2])}.\n\n'),

    lambda num1, num2, g: (
        f'Inputs: {num1} {num2}\n', f'Answer: {g([num1, num2])}\n\n'),

    lambda num1, num2, g: (
        f'The inputs are {num1} {num2}.', f' The answer is {g([num1, num2])}\n\n'),
]
SUFFIXES_TWO_NUMS = [
        # "The function mapping the input to the output is",
        "The function f(x) returns the",
        "To compute the answer from the input number x, return",
        "To compute the answer f(x) from the input number x, return",
        # "To find the output, take the number in the question and use the",
        # "To get the answer, take the number in the question and",
        "To calculate the answer, take the input and",
        "The relationship between the number in the question and the answer is:",
        "To get the answer,",
]

"""Note: tasks here consist of
(i) a function that returns data given the right inputs
(ii) a function that evaluates whether the output is correct
(iii) a function that computes the output (given a list)
"""
TASKS_TWO_NUMS = {
    'add_two': {
        'prompt_template_funcs': PROMPT_TEMPLATE_TWO_NUMS,
        'check_answer_func': r'add|sum',
        'gen_func': sum
    },
    'multiply_two': {
        'prompt_template_funcs': PROMPT_TEMPLATE_TWO_NUMS,
        'check_answer_func': r'multiply|product',
        'gen_func': np.prod
    },
    'divide_two': {
        'prompt_template_funcs': PROMPT_TEMPLATE_TWO_NUMS,
        'check_answer_func': r'divide|into',
        'gen_func': lambda l: f'{l[0]}/{l[1]}'
    },
    'subtract_two': {
        'prompt_template_funcs': PROMPT_TEMPLATE_TWO_NUMS,
        'check_answer_func': r'subtract|difference',
        'gen_func': lambda l: l[0] - l[1]
    },
    'max_two': {
        'prompt_template_funcs': PROMPT_TEMPLATE_TWO_NUMS,
        'check_answer_func': r'max|large|greate|big',
        'gen_func': max
    },

    # this one finds solutions like "subtract from the first"
    'first_two': {
        'prompt_template_funcs': PROMPT_TEMPLATE_TWO_NUMS,
        'check_answer_func': r'first|begin|original',
        'gen_func': lambda x: x[0]
    },

    'SUFFIXES': SUFFIXES_TWO_NUMS,    
}