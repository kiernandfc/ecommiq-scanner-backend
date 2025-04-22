#!/usr/bin/env python
"""
Test script for HTML report generation
This script takes a JSON report and generates an HTML summary report using the OpenAI API
"""

import os
import sys
import argparse
import json
import logging
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the function we want to test
from brain.price_change_report import generate_html_report

def configure_logger(logger_name, debug=False):
    """
    Configure a logger with console and file handlers
    
    Args:
        logger_name: Name for the logger
        debug: Whether to enable debug-level logging
    
    Returns:
        Configured logger instance
    """
    # Create logger
    logger = logging.getLogger(logger_name)
    
    # Clear any existing handlers to prevent duplicates
    if logger.handlers:
        logger.handlers = []
    
    # Set the log level
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    
    # Create console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG if debug else logging.INFO)
    console_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console.setFormatter(console_format)
    logger.addHandler(console)
    
    # Create file handler
    try:
        file_handler = logging.FileHandler(f"{logger_name}.log")
        file_handler.setLevel(logging.DEBUG if debug else logging.INFO)
        file_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Could not create log file: {e}")
    
    # Prevent propagation to root logger to avoid duplicate logs
    logger.propagate = False
    
    return logger

def main():
    """Main function to test HTML report generation from JSON data"""
    # Setup argument parser
    parser = argparse.ArgumentParser(description='Test HTML report generation from JSON data')
    parser.add_argument('--input', '-i', dest='input_file', 
                        default='reports/price_change_report_20250421_145017.json',
                        help='Path to input JSON file')
    parser.add_argument('--output', '-o', dest='output_file',
                        help='Path to output HTML file (default: uses input filename with _summary.html extension)')
    parser.add_argument('--debug', '-d', action='store_true',
                        help='Enable debug logging')
    
    args = parser.parse_args()
    
    # Setup logger
    logger = configure_logger("test_html_generator", args.debug)
    
    # Determine output file name if not provided
    if not args.output_file:
        input_base = os.path.splitext(args.input_file)[0]
        args.output_file = f"{input_base}_summary_test.html"
    
    logger.info(f"Reading JSON data from: {args.input_file}")
    logger.info(f"Output HTML will be saved to: {args.output_file}")
    
    try:
        # Read JSON content from file
        with open(args.input_file, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        
        logger.info(f"Successfully read JSON data")
        
        # Generate the HTML report
        logger.info("Generating HTML report from JSON data...")
        html_file_path = generate_html_report(json_data, args.input_file)
        
        if html_file_path:
            logger.info(f"HTML generation successful. Output saved to: {html_file_path}")
            print(f"SUCCESS: HTML report generated and saved to {html_file_path}")
        else:
            logger.error("Failed to generate HTML report")
            print("ERROR: Failed to generate HTML report")
            sys.exit(1)
        
    except FileNotFoundError:
        error_msg = f"Input file not found: {args.input_file}"
        logger.error(error_msg)
        print(f"ERROR: {error_msg}")
        sys.exit(1)
    except json.JSONDecodeError:
        error_msg = f"Invalid JSON in input file: {args.input_file}"
        logger.error(error_msg)
        print(f"ERROR: {error_msg}")
        sys.exit(1)
    except Exception as e:
        error_msg = f"Error generating HTML report: {e}"
        logger.error(error_msg, exc_info=True)
        print(f"ERROR: {error_msg}")
        sys.exit(1)

if __name__ == "__main__":
    main() 