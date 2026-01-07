#!/usr/bin/env python3
"""
XCode Assets Color Extractor
Extracts all colors from XCode .xcassets and outputs to JSON with Hex values
Supports both decimal (0.200) and hex (0x2E) component formats
"""

import json
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any


def parse_component_value(value: str) -> float:
    """
    Parse color component value - handles both decimal strings and hex strings
    
    Args:
        value: Component value as string (e.g., "0.200" or "0x2E")
    
    Returns:
        Float value between 0 and 1
    """
    value = value.strip().strip('"')
    
    # Check if it's hex format (0x2E)
    if value.startswith('0x') or value.startswith('0X'):
        # Convert hex to int, then normalize to 0-1 range
        hex_value = int(value, 16)
        return hex_value / 255.0
    
    # Otherwise treat as decimal string
    return float(value)


def rgb_to_hex(r: float, g: float, b: float, a: float = 1.0) -> str:
    """
    Convert RGB(A) values (0-1 range) to hex color code
    
    Args:
        r, g, b: Color components in 0-1 range
        a: Alpha component in 0-1 range (default 1.0)
    
    Returns:
        Hex color string (e.g., "#3366CC" or "#3366CCFF" if alpha < 1.0)
    """
    # Clamp values to 0-1 range
    r = max(0.0, min(1.0, r))
    g = max(0.0, min(1.0, g))
    b = max(0.0, min(1.0, b))
    a = max(0.0, min(1.0, a))
    
    # Convert to 0-255 range and format as hex
    r_hex = int(round(r * 255))
    g_hex = int(round(g * 255))
    b_hex = int(round(b * 255))
    
    # Include alpha in hex if it's not fully opaque
    if a < 1.0:
        a_hex = int(round(a * 255))
        return f"#{r_hex:02X}{g_hex:02X}{b_hex:02X}{a_hex:02X}"
    
    return f"#{r_hex:02X}{g_hex:02X}{b_hex:02X}"


def grayscale_to_hex(white: float, a: float = 1.0) -> str:
    """
    Convert grayscale value to hex color code
    
    Args:
        white: Grayscale value in 0-1 range
        a: Alpha component in 0-1 range (default 1.0)
    
    Returns:
        Hex color string
    """
    return rgb_to_hex(white, white, white, a)


def parse_color_to_hex(color_data: Dict[str, Any]) -> tuple[str, Dict[str, str]]:
    """
    Parse color data from XCode asset and convert to hex
    
    Args:
        color_data: Color dictionary from Contents.json
    
    Returns:
        Tuple of (hex_string, components_dict)
    """
    color_space = color_data.get('color-space', 'srgb')
    components = color_data.get('components', {})
    
    # Parse alpha (always decimal format)
    alpha = float(components.get('alpha', '1.0').strip('"'))
    
    # Handle different color spaces
    if color_space in ['srgb', 'display-p3', 'extended-srgb', 'extended-linear-srgb']:
        # Parse RGB components (can be decimal or hex)
        red = parse_component_value(components.get('red', '0'))
        green = parse_component_value(components.get('green', '0'))
        blue = parse_component_value(components.get('blue', '0'))
        
        hex_color = rgb_to_hex(red, green, blue, alpha)
        
        return hex_color, {
            'red': f"{red:.3f}",
            'green': f"{green:.3f}",
            'blue': f"{blue:.3f}",
            'alpha': f"{alpha:.3f}"
        }
    
    elif color_space in ['gray-gamma-22', 'extended-gray']:
        # Parse grayscale component (can be decimal or hex)
        white = parse_component_value(components.get('white', '0'))
        
        hex_color = grayscale_to_hex(white, alpha)
        
        return hex_color, {
            'white': f"{white:.3f}",
            'alpha': f"{alpha:.3f}"
        }
    
    else:
        # Unknown color space - return raw data
        print(f"Warning: Unknown color space '{color_space}', returning raw components")
        return "#000000", components


def extract_color_variants(color_item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract all color variants (light, dark, high contrast, etc.)
    
    Args:
        color_item: Single color entry from Contents.json
    
    Returns:
        Dictionary containing variant information
    """
    result = {
        'light': None,
        'dark': None,
        'other_variants': []
    }
    
    # Get appearances
    appearances = color_item.get('appearances', [])
    color_data = color_item.get('color')
    idiom = color_item.get('idiom', 'universal')
    
    if not color_data:
        return result
    
    # Parse the color
    hex_color, components = parse_color_to_hex(color_data)
    
    # Build color info
    color_info = {
        'hex': hex_color,
        'color_space': color_data.get('color-space', 'srgb'),
        'components': components,
        'idiom': idiom
    }
    
    # Determine appearance type
    if not appearances:
        # No appearance specified = light mode (default)
        result['light'] = color_info
    else:
        # Check appearance attributes
        for appearance in appearances:
            appearance_value = appearance.get('value')
            
            if appearance_value == 'dark':
                result['dark'] = color_info
            elif appearance_value == 'light':
                result['light'] = color_info
            else:
                # Other variants (high contrast, etc.)
                result['other_variants'].append({
                    'appearance': appearance_value,
                    **color_info
                })
    
    return result


def find_color_sets(assets_path: Path) -> List[Path]:
    """
    Recursively find all .colorset directories in the assets catalog
    
    Args:
        assets_path: Path to .xcassets directory
    
    Returns:
        List of paths to .colorset directories
    """
    colorsets = []
    
    # Walk through all directories
    for root, dirs, files in os.walk(assets_path):
        for dir_name in dirs:
            if dir_name.endswith('.colorset'):
                colorset_path = Path(root) / dir_name
                colorsets.append(colorset_path)
    
    return colorsets


def extract_colors_from_colorset(colorset_path: Path) -> Optional[Dict[str, Any]]:
    """
    Extract color information from a single .colorset
    
    Args:
        colorset_path: Path to .colorset directory
    
    Returns:
        Dictionary containing color data or None if parsing fails
    """
    contents_file = colorset_path / 'Contents.json'
    
    if not contents_file.exists():
        print(f"Warning: Contents.json not found in {colorset_path}")
        return None
    
    try:
        with open(contents_file, 'r', encoding='utf-8') as f:
            contents = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse {contents_file}: {e}")
        return None
    except Exception as e:
        print(f"Error: Failed to read {contents_file}: {e}")
        return None
    
    # Extract color name from directory
    color_name = colorset_path.name.replace('.colorset', '')
    
    # Get all color entries
    colors = contents.get('colors', [])
    
    if not colors:
        print(f"Warning: No colors found in {colorset_path}")
        return None
    
    # Build color data structure
    color_data = {
        'name': color_name,
        'light': None,
        'dark': None,
        'other_variants': [],
        'metadata': {
            'info': contents.get('info', {}),
            'properties': contents.get('properties', {})
        }
    }
    
    # Process each color variant
    for color_item in colors:
        variants = extract_color_variants(color_item)
        
        # Merge variants
        if variants['light'] and not color_data['light']:
            color_data['light'] = variants['light']
        
        if variants['dark'] and not color_data['dark']:
            color_data['dark'] = variants['dark']
        
        color_data['other_variants'].extend(variants['other_variants'])
    
    return color_data


def extract_all_colors(assets_path: Path) -> Dict[str, Any]:
    """
    Extract all colors from XCode assets catalog
    
    Args:
        assets_path: Path to .xcassets directory
    
    Returns:
        Dictionary containing all extracted colors
    """
    # Validate path
    if not assets_path.exists():
        raise FileNotFoundError(f"Assets path does not exist: {assets_path}")
    
    if not assets_path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {assets_path}")
    
    if not str(assets_path).endswith('.xcassets'):
        print(f"Warning: Path doesn't end with .xcassets: {assets_path}")
    
    # Find all colorsets
    print(f"Scanning for colorsets in: {assets_path}")
    colorsets = find_color_sets(assets_path)
    print(f"Found {len(colorsets)} colorset(s)")
    
    # Extract colors from each colorset
    colors = []
    for colorset_path in colorsets:
        print(f"Processing: {colorset_path.name}")
        color_data = extract_colors_from_colorset(colorset_path)
        if color_data:
            colors.append(color_data)
    
    # Build final output
    output = {
        'source': str(assets_path.absolute()),
        'total_colors': len(colors),
        'extraction_date': datetime.utcnow().isoformat() + 'Z',
        'colors': colors
    }
    
    return output


def main():
    """Main entry point for the script"""
    parser = argparse.ArgumentParser(
        description='Extract colors from XCode Assets catalog and output as JSON with Hex values'
    )
    parser.add_argument(
        'assets_path',
        type=str,
        help='Path to .xcassets directory'
    )
    parser.add_argument(
        '-o', '--output',
        type=str,
        default='colors.json',
        help='Output JSON file path (default: colors.json)'
    )
    
    args = parser.parse_args()
    
    # Convert to Path object
    assets_path = Path(args.assets_path)
    output_path = Path(args.output)
    
    try:
        # Extract colors
        print("Starting color extraction...")
        color_data = extract_all_colors(assets_path)
        
        # Write to output file
        print(f"\nWriting output to: {output_path}")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(color_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Successfully extracted {color_data['total_colors']} color(s)")
        print(f"📄 Output saved to: {output_path.absolute()}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
