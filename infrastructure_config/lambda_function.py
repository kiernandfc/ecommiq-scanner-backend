"""
AWS Lambda entry point for kitchen cost calculator.
This file imports and delegates to the main handler in kitchen_cost_calculator.py
"""

from kitchen_cost_calculator import lambda_handler

# AWS Lambda will call this function
def lambda_handler(event, context):
    """
    Entry point for AWS Lambda. Delegates to the main handler.
    """
    from kitchen_cost_calculator import lambda_handler as main_handler
    return main_handler(event, context)
