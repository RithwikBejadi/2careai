import ast
import os

def strip_comments_and_docstrings(source):
    # Parse source into an AST
    try:
        parsed = ast.parse(source)
    except Exception as e:
        return source # keep original if parse fails

    # Find the docstrings
    for node in ast.walk(parsed):
        if not isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef, ast.Module)):
            continue
        
        if not len(node.body):
            continue
            
        if not isinstance(node.body[0], ast.Expr):
            continue
            
        if not hasattr(node.body[0], 'value') or not isinstance(node.body[0].value, ast.Constant):
            continue
            
        if not isinstance(node.body[0].value.value, str):
            continue
            
        # Try to strip docstrings by assigning an empty string to them or removing them
        # (A bit complex via ast unparse so let's use a simpler token approach)
        node.body[0].value.value = ""

    # Unparse back to source code (requires Python 3.9+)
    try:
        return ast.unparse(parsed)
    except Exception:
        return source

import tokenize
from io import BytesIO

def remove_comments_and_docstrings(source):
    io_obj = BytesIO(source.encode('utf-8'))
    out = ""
    prev_toktype = tokenize.INDENT
    last_lineno = -1
    last_col = 0
    for tok in tokenize.tokenize(io_obj.readline):
        token_type = tok.type
        token_string = tok.string
        start_line, start_col = tok.start
        end_line, end_col = tok.end
        
        if start_line > last_lineno:
            last_col = 0
        if start_col > last_col:
            out += (" " * (start_col - last_col))

        if token_type == tokenize.COMMENT:
            pass
        elif token_type == tokenize.STRING:
            if prev_toktype != tokenize.INDENT:
                if prev_toktype != tokenize.NEWLINE:
                    if start_col > 0:
                        out += token_string
        else:
            out += token_string
            
        prev_toktype = token_type
        last_col = end_col
        last_lineno = end_line
    return out

def process_file(filepath):
    with open(filepath, 'r') as f:
        source = f.read()
    
    # Strip comments and docstrings
    import io
    result = []
    g = tokenize.tokenize(io.BytesIO(source.encode('utf-8')).readline)
    prev_toktype = tokenize.INDENT
    last_lineno = -1
    last_col = 0
        
    for tok in g:
        token_type = tok.type
        token_string = tok.string
        start_line, start_col = tok.start
        end_line, end_col = tok.end
        
        if start_line > last_lineno:
            last_col = 0
        if start_col > last_col:
            result.append(" " * (start_col - last_col))

        if token_type == tokenize.COMMENT:
            pass
        elif token_type == tokenize.STRING:
            if prev_toktype != tokenize.INDENT and prev_toktype != tokenize.NEWLINE and start_col > 0:
                # We skip docstrings which are usually the first thing after a newline/indent
                # But keep regular strings
                result.append(token_string)
            elif prev_toktype == tokenize.EQUAL or prev_toktype == tokenize.LPAR or prev_toktype == tokenize.COMMA:
                result.append(token_string)
            else:
                # Also need to check if it's an assignment like x = """foo"""
                result.append(token_string)
        else:
            result.append(token_string)
            
        prev_toktype = token_type
        last_col = end_col
        last_lineno = end_line
        
    with open(filepath, 'w') as f:
        f.write("".join(result))

for root, _, files in os.walk('backend'):
    if "venv" in root: continue
    for file in files:
        if file.endswith('.py'):
            # Just do a safe AST unparse
            filepath = os.path.join(root, file)
            with open(filepath, 'r') as f:
                src = f.read()
            try:
                tree = ast.parse(src)
                clean_src = ast.unparse(tree)
                with open(filepath, 'w') as f:
                    f.write(clean_src)
            except Exception as e:
                print(f"Skipping {filepath} due to AST error {e}")
