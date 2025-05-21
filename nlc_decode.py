import os
import base64
import json
from PIL import Image
import io

def hex_to_string(hex_data):
    """Convert hexadecimal data to a string, truncating at newline if present."""
    try:
        byte_data = bytes.fromhex(hex_data)  # Convert hex to bytes
        string_data = byte_data.decode('utf-8')  # Decode bytes to string
        
        # Find and truncate at newline character
        newline_index = string_data.find('\n')
        if newline_index != -1:
            string_data = string_data[:newline_index]
        return string_data

    except Exception as e:
        print(f"Failed to convert hex to string: {e}")
        return None

def process_file(filename):
    """Read a file, convert hexadecimal to string, parse JSON to extract Base64 data, and generate an image."""
    if not os.path.exists(filename):
        print(f"File {filename} does not exist!")
        return

    base64_strings = []  # Store all Base64 string fragments

    with open(filename, 'r', encoding='utf-8') as file:
        for line_num, line in enumerate(file, start=1):
            line = line.strip()  # Remove leading and trailing whitespace
            if line:
                try:
                    # Convert hex data to a string
                    json_string = hex_to_string(line)
                    if not json_string:
                        print(f"Hex to string conversion failed on line {line_num}!")
                        continue

                    # Attempt to parse as JSON
                    data = json.loads(json_string)
                    for key, value in data.items():
                        if isinstance(value, str):
                            # Add Base64 data fragments to the list
                            print(f"Base64 data size: {len(value)}")  # Print the size of Base64 data
                            base64_strings.append(value)
                except json.JSONDecodeError:
                    print(f"JSON parsing failed on line {line_num}: {json_string}")
                except Exception as e:
                    print(f"Error processing line {line_num}: {e}")
    
    # Combine Base64 strings and save as an image
    save_image_from_list(base64_strings)

def save_image_from_list(base64_strings):
    """Decode combined Base64 data fragments and save as a BMP image."""
    try:
        # Combine all Base64 data fragments into a single string
        complete_base64_data = ''.join(base64_strings)
        # Decode Base64 data
        image_binary = base64.b64decode(complete_base64_data)
        # Use Pillow to convert binary data into an image
        image = Image.open(io.BytesIO(image_binary))
        # Save as BMP format
        filename = "complete_image.bmp"
        image.save(filename, format='BMP')
        print(f"Image saved to {filename}")
    except Exception as e:
        print(f"Error saving image: {e}")

if __name__ == '__main__':
    # Input file path
    input_filename = 'uart_nlc.txt'

    # Process the file content
    process_file(input_filename)
