"""
Multi-language AST parser for code analysis.

Extracts code units (functions, classes, methods) from source files
with metadata including complexity metrics and location information.
"""

import ast
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set, Dict
import re


@dataclass
class CodeUnit:
    """Represents a single analyzable code unit (function/class/method)"""
    name: str
    file_path: str
    start_line: int
    end_line: int
    code: str
    language: str
    complexity: int
    loc: int  
    dependencies: List[str]
    unit_type: str  
    suspicious_tags: List[str] = None  
    imports: Dict[str, str] = None 
    parent_name: Optional[str] = None 

    def __post_init__(self):
        if self.suspicious_tags is None:
            self.suspicious_tags = []
        if self.imports is None:
            self.imports = {}


class ASTParser(ABC):
    """Base class for language-specific AST parsers"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.content = self._read_file()
        self.lines = self.content.splitlines()
    
    def _read_file(self) -> str:
        """Read file content with error handling"""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception:
            return ""
    
    def _extract_code_lines(self, start_line: int, end_line: int) -> str:
        """Extract code from specific line range"""
        if not self.lines:
            return ""
        # Lines are 1-indexed
        start_idx = max(0, start_line - 1)
        end_idx = min(len(self.lines), end_line)
        return "\n".join(self.lines[start_idx:end_idx])
    
    def _count_loc(self, code: str) -> int:
        """Count non-blank, non-comment lines"""
        lines = code.splitlines()
        return len([line for line in lines if line.strip() and not self._is_comment_line(line)])
    
    @abstractmethod
    def _is_comment_line(self, line: str) -> bool:
        """Check if a line is a comment"""
        pass
    
    @abstractmethod
    def parse(self) -> List[CodeUnit]:
        """Parse file and extract code units"""
        pass


class PythonASTParser(ASTParser):
    """Python AST parser using built-in ast module"""
    
    def _is_comment_line(self, line: str) -> bool:
        stripped = line.strip()
        return stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''")
    
    def _calculate_complexity(self, node: ast.AST) -> int:
        """Calculate cyclomatic complexity for a Python AST node"""
        complexity = 1
        for child in ast.walk(node):
            # Each decision point adds 1 to complexity
            if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor,
                                 ast.ExceptHandler, ast.With, ast.AsyncWith,
                                 ast.Assert, ast.BoolOp)):
                complexity += 1
            elif isinstance(child, ast.FunctionDef) and child != node:
                # Don't count nested functions
                continue
        return complexity
    
    def _extract_dependencies(self, node: ast.AST) -> List[str]:
        """Extract function calls and imports from node"""
        deps = set()
        
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    deps.add(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    deps.add(child.func.attr)
        
        return sorted(list(deps))
    
    def _extract_imports(self, tree: ast.AST) -> Dict[str, str]:
        """Extract top-level imports from the AST"""
        imports = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    # import json -> json: json
                    # import json as j -> j: json
                    name = alias.asname or alias.name
                    imports[name] = alias.name
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    # from os import path -> path: os.path
                    # from os import path as p -> p: os.path
                    full_name = f"{module}.{alias.name}" if module else alias.name
                    name = alias.asname or alias.name
                    imports[name] = full_name
            
        return imports

    def parse(self) -> List[CodeUnit]:
        """Parse Python file and extract functions/classes using recursive traversal"""
        if not self.content.strip():
            return []
        
        try:
            tree = ast.parse(self.content)
        except SyntaxError:
            return []
        
        units = []
        global_imports = self._extract_imports(tree)
        
        def visit_node(node, parent_name=None):
            # Check for functions and classes
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                # Get the actual line numbers
                start_line = node.lineno
                end_line = node.end_lineno or start_line
                
                # Extract code for this unit
                code = self._extract_code_lines(start_line, end_line)
                
                # Determine unit type
                is_class = isinstance(node, ast.ClassDef)
                unit_type = "class" if is_class else ("method" if parent_name else "function")
                
                # Calculate metrics
                complexity = self._calculate_complexity(node)
                loc = self._count_loc(code)
                deps = self._extract_dependencies(node)
                tags = self._identify_suspicious_tags(node, code)
                
                units.append(CodeUnit(
                    name=node.name,
                    file_path=self.file_path,
                    start_line=start_line,
                    end_line=end_line,
                    code=code,
                    language="python",
                    complexity=complexity,
                    loc=loc,
                    dependencies=deps,
                    unit_type=unit_type,
                    suspicious_tags=tags,
                    imports=global_imports,
                    parent_name=parent_name
                ))
                
                # If it's a class, recurse into children with this class as parent
                if is_class:
                    for child in node.body:
                        visit_node(child, parent_name=node.name)
                
                
            else:
                # Continue searching children for definitions (e.g. inside if __name__ == "__main__": )
                if hasattr(node, "body") and isinstance(node.body, list):
                     for child in node.body:
                        visit_node(child, parent_name)
                elif hasattr(node, "body"): # e.g. If/For/etc
                     visit_node(node.body, parent_name)
                
                if hasattr(node, "orelse") and isinstance(node.orelse, list):
                    for child in node.orelse:
                        visit_node(child, parent_name)

        # Start traversal
        for node in tree.body:
            visit_node(node)
        
        return units

    def _identify_suspicious_tags(self, node: ast.AST, code: str) -> List[str]:
        """Identify suspicious patterns that might affect energy efficiency"""
        tags = set()
        
        # IO / Network / DB keywords (simple string matching first)
        code_lower = code.lower()
        
        # DATA_ACCESS: Database interaction
        if any(w in code_lower for w in ['execute', 'cursor', 'commit', 'rollback', 'fetch', 'query', 'select ', 'insert ', 'update ', 'delete ']):
            tags.add('DATA_ACCESS')
            
        # IO: File/Network
        if any(w in code_lower for w in ['open(', 'read', 'write', 'socket', 'http', 'request', 'post', 'get']):
            tags.add('IO')

        # WAIT: Sleep/Delay
        if any(w in code_lower for w in ['sleep', 'wait', 'delay', 'timeout']):
            tags.add('WAIT')
            
        # COMPUTATION: Heavy math
        if any(w in code_lower for w in ['numpy', 'pandas', 'math', 'calculate', 'compute', 'matrix']):
            tags.add('COMPUTATION')

        # DEEPCOPY
        if 'deepcopy' in code_lower:
            tags.add('COMPUTATION')

        # TRAVERSE AST for structural tags
        for child in ast.walk(node):
            # LOOP
            if isinstance(child, (ast.For, ast.AsyncFor, ast.While)):
                tags.add('LOOP')
            
            # THREAD
            if isinstance(child, (ast.AsyncFunctionDef, ast.AsyncWith, ast.AsyncFor, ast.Await)):
                tags.add('THREAD')
                
        return sorted(list(tags))


class JavaScriptASTParser(ASTParser):
    """JavaScript/TypeScript parser using esprima"""
    
    def _is_comment_line(self, line: str) -> bool:
        stripped = line.strip()
        return stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*')
    
    def parse(self) -> List[CodeUnit]:
        """Parse JavaScript/TypeScript file"""
        try:
            import esprima
        except ImportError:
            # Fallback: return whole file as single unit
            return self._fallback_parse()
        
        if not self.content.strip():
            return []
        
        try:
            tree = esprima.parseScript(self.content, {'loc': True})
        except Exception:
            return self._fallback_parse()
        
        units = []
        
        def walk(node, depth=0):
            if hasattr(node, 'type'):
                if node.type == 'FunctionDeclaration' or node.type == 'FunctionExpression':
                    if hasattr(node, 'id') and node.id:
                        name = node.id.name
                    else:
                        name = "<anonymous>"
                    
                    if hasattr(node, 'loc') and node.loc:
                        start_line = node.loc.start.line
                        end_line = node.loc.end.line
                        
                        code = self._extract_code_lines(start_line, end_line)
                        complexity = self._estimate_complexity(code)
                        loc = self._count_loc(code)
                        tags = self._estimate_tags(code)
                        
                        units.append(CodeUnit(
                            name=name,
                            file_path=self.file_path,
                            start_line=start_line,
                            end_line=end_line,
                            code=code,
                            language="javascript",
                            complexity=complexity,
                            loc=loc,
                            dependencies=[],
                            unit_type="function",
                            suspicious_tags=tags
                        ))
            
            # Recursively walk children
            if hasattr(node, 'body'):
                if isinstance(node.body, list):
                    for child in node.body:
                        walk(child, depth + 1)
                else:
                    walk(node.body, depth + 1)
        
        walk(tree)
        return units
    
    def _estimate_complexity(self, code: str) -> int:
        """Estimate cyclomatic complexity from code text"""
        complexity = 1
        keywords = ['if', 'else if', 'for', 'while', 'case', '&&', '||', '?']
        for keyword in keywords:
            complexity += code.count(keyword)
        return complexity
    
    def _estimate_tags(self, code: str) -> List[str]:
        tags = set()
        code_lower = code.lower()
        
        if any(w in code_lower for w in ['for', 'while', 'map', 'reduce', 'foreach']):
            tags.add('LOOP')
        if any(w in code_lower for w in ['fetch', 'axios', 'http', 'xmlhttprequest', 'ajax']):
            tags.add('IO')
        if any(w in code_lower for w in ['settimeout', 'setinterval', 'sleep', 'wait']):
            tags.add('WAIT')
        if any(w in code_lower for w in ['async', 'await', 'promise', 'then']):
            tags.add('THREAD')
        if any(w in code_lower for w in ['sql', 'query', 'db', 'database', 'mongo', 'redis']):
            tags.add('DATA_ACCESS')
            
        return sorted(list(tags))
    
    def _fallback_parse(self) -> List[CodeUnit]:
        """Fallback: treat entire file as single unit"""
        return []


class JavaASTParser(ASTParser):
    """Java parser using javalang"""
    
    def _is_comment_line(self, line: str) -> bool:
        stripped = line.strip()
        return stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*')
    
    def parse(self) -> List[CodeUnit]:
        """Parse Java file"""
        try:
            import javalang
        except ImportError:
            return []
        
        if not self.content.strip():
            return []
        
        try:
            tree = javalang.parse.parse(self.content)
        except Exception:
            return []
        
        units = []
        
        for path, node in tree.filter(javalang.tree.MethodDeclaration):
            
            method_pattern = rf'\b{re.escape(node.name)}\s*\('
            
            for i, line in enumerate(self.lines, 1):
                if re.search(method_pattern, line):
                    
                    start_line = i
                    end_line = self._find_method_end(start_line)
                    
                    code = self._extract_code_lines(start_line, end_line)
                    complexity = self._estimate_complexity(code)
                    loc = self._count_loc(code)
                    tags = self._estimate_tags(code)
                    
                    units.append(CodeUnit(
                        name=node.name,
                        file_path=self.file_path,
                        start_line=start_line,
                        end_line=end_line,
                        code=code,
                        language="java",
                        complexity=complexity,
                        loc=loc,
                        dependencies=[],
                        unit_type="method",
                        suspicious_tags=tags
                    ))
                    break
        
        return units
    
    def _find_method_end(self, start_line: int) -> int:
        """Find the end of a method by counting braces"""
        brace_count = 0
        in_method = False
        
        for i in range(start_line - 1, len(self.lines)):
            line = self.lines[i]
            for char in line:
                if char == '{':
                    brace_count += 1
                    in_method = True
                elif char == '}':
                    brace_count -= 1
                    if in_method and brace_count == 0:
                        return i + 1
        
        return len(self.lines)
    
    def _estimate_complexity(self, code: str) -> int:
        """Estimate cyclomatic complexity"""
        complexity = 1
        keywords = ['if', 'else if', 'for', 'while', 'case', 'catch', '&&', '||', '?']
        for keyword in keywords:
            complexity += code.count(keyword)
        return complexity

    def _estimate_tags(self, code: str) -> List[str]:
        tags = set()
        code_lower = code.lower()
        
        if any(w in code_lower for w in ['for', 'while', 'do']):
            tags.add('LOOP')
        if any(w in code_lower for w in ['thread', 'runnable', 'future', 'completablefuture']):
            tags.add('THREAD')
        if any(w in code_lower for w in ['sleep', 'wait', 'delay']):
            tags.add('WAIT')
        if any(w in code_lower for w in ['file', 'stream', 'socket', 'http', 'net']):
            tags.add('IO')
        if any(w in code_lower for w in ['sql', 'jdbc', 'query', 'resultset', 'execute']):
            tags.add('DATA_ACCESS')
            
        return sorted(list(tags))


class CppASTParser(ASTParser):
    """C/C++ parser using tree-sitter"""
    
    def _is_comment_line(self, line: str) -> bool:
        stripped = line.strip()
        return stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*')
    
    def parse(self) -> List[CodeUnit]:
        """Parse C/C++ file using tree-sitter"""
        try:
            from tree_sitter import Language, Parser
            import tree_sitter_c
            import tree_sitter_cpp
        except ImportError:
            return []
        
        if not self.content.strip():
            return []
        
        # Determine if C or C++
        is_cpp = self.file_path.endswith('.cpp') or self.file_path.endswith('.hpp')
        
        try:
            if is_cpp:
                language = Language(tree_sitter_cpp.language())
            else:
                language = Language(tree_sitter_c.language())
            
            parser = Parser(language)
            tree = parser.parse(bytes(self.content, 'utf8'))
        except Exception:
            return []
        
        units = []
        
        def visit_node(node):
            if node.type == 'function_definition':
                # Extract function name
                declarator = node.child_by_field_name('declarator')
                if declarator:
                    # Find the identifier
                    name = self._extract_function_name(declarator)
                    
                    start_line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    
                    code = self._extract_code_lines(start_line, end_line)
                    complexity = self._estimate_complexity(code)
                    loc = self._count_loc(code)
                    tags = self._estimate_tags(code)
                    
                    units.append(CodeUnit(
                        name=name,
                        file_path=self.file_path,
                        start_line=start_line,
                        end_line=end_line,
                        code=code,
                        language="cpp" if is_cpp else "c",
                        complexity=complexity,
                        loc=loc,
                        dependencies=[],
                        unit_type="function",
                        suspicious_tags=tags
                    ))
            
            # Visit children
            for child in node.children:
                visit_node(child)
        
        visit_node(tree.root_node)
        return units
    
    def _extract_function_name(self, declarator) -> str:
        """Extract function name from declarator node"""
        if declarator.type == 'function_declarator':
            for child in declarator.children:
                if child.type == 'identifier':
                    return child.text.decode('utf8')
                elif child.type == 'function_declarator':
                    return self._extract_function_name(child)
        elif declarator.type == 'identifier':
            return declarator.text.decode('utf8')
        
        return "<unknown>"
    
    def _estimate_complexity(self, code: str) -> int:
        """Estimate cyclomatic complexity"""
        complexity = 1
        keywords = ['if', 'else if', 'for', 'while', 'case', 'catch', '&&', '||', '?']
        for keyword in keywords:
            complexity += code.count(keyword)
        return complexity

    def _estimate_tags(self, code: str) -> List[str]:
        tags = set()
        code_lower = code.lower()
        
        if any(w in code_lower for w in ['for', 'while', 'do']):
            tags.add('LOOP')
        if any(w in code_lower for w in ['thread', 'mutex', 'future', 'async']):
            tags.add('THREAD')
        if any(w in code_lower for w in ['sleep', 'usleep', 'wait']):
            tags.add('WAIT')
        if any(w in code_lower for w in ['file', 'fopen', 'read', 'write', 'socket']):
            tags.add('IO')
            
        return sorted(list(tags))


def get_parser(file_path: str) -> Optional[ASTParser]:
    """Factory function to get appropriate parser for file type"""
    ext = Path(file_path).suffix.lower()
    
    if ext == '.py':
        return PythonASTParser(file_path)
    elif ext in ['.js', '.ts', '.jsx', '.tsx']:
        return JavaScriptASTParser(file_path)
    elif ext == '.java':
        return JavaASTParser(file_path)
    elif ext in ['.c', '.cpp', '.cc', '.cxx', '.h', '.hpp']:
        return CppASTParser(file_path)
    
    return None


def parse_file(file_path: str) -> List[CodeUnit]:
    """
    Parse a source file and extract code units.
    
    Returns:
        List of CodeUnit objects, or empty list if parsing fails
    """
    parser = get_parser(file_path)
    if parser is None:
        return []
    
    try:
        return parser.parse()
    except Exception:
        return []
