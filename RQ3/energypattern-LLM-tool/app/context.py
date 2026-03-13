from typing import Dict, List, Set, Optional
from app.ast_parser import CodeUnit

class SymbolTable:
    """
    Indexes code units by name to establish a project-wide symbol table.
    Used to resolve dependencies between functions.
    """
    def __init__(self):
        # Map function/class name -> List of CodeUnits (list to handle duplicates/overloads)
        self.symbols: Dict[str, List[CodeUnit]] = {}

    def add_unit(self, unit: CodeUnit):
        """Register a code unit in the symbol table."""
        if unit.name not in self.symbols:
            self.symbols[unit.name] = []
        self.symbols[unit.name].append(unit)

    def get_units(self, name: str) -> List[CodeUnit]:
        """Retrieve code units by name. Returns empty list if not found."""
        return self.symbols.get(name, [])
    
    def clear(self):
        self.symbols.clear()


class ContextBuilder:
    """
    Builds context strings for LLM analysis by resolving dependencies.
    """
    def __init__(self, symbol_table: SymbolTable):
        self.symbol_table = symbol_table

    def get_context_for_unit(self, unit: CodeUnit) -> str:
        """
        Generate a string containing the code of this unit's dependencies.
        Only includes dependencies found in the project (SymbolTable).
        """
        context_parts = []
        processed_symbols = set()

        # 1. Resolve Dependencies
        # Sort dependencies to ensure deterministic output
        deps = sorted(unit.dependencies)
        
        for dep_name in deps:
            # Avoid self-reference or duplicate inclusion
            if dep_name == unit.name or dep_name in processed_symbols:
                continue
            
            processed_symbols.add(dep_name)
            
            # Lookup the dependency in our project symbol table
            found_units = self.symbol_table.get_units(dep_name)

            # --- Import Resolution ---
            # If we know exactly where it comes from via imports, filter candidates
            if dep_name in unit.imports and found_units:
                full_import_path = unit.imports[dep_name]
                import_path_parts = full_import_path.split('.')
                
                better_matches = []
                for candidate in found_units:
                    expected_filename = import_path_parts[-1] + ".py"
                    expected_filename = import_path_parts[-1] + ".py"
                    if candidate.file_path.endswith(expected_filename):
                        better_matches.append(candidate)
                        
                if better_matches:
                    found_units = better_matches

            
            # If not found, it's likely an external library (e.g., random.randint, time.sleep)
            # We strictly ignore these to avoid analyzing library code.
            if not found_units:
                continue
            
            # Heuristic: If multiple units match (e.g. same name in diff files),
            # include them all. A more advanced system would track imports.
            for dep_unit in found_units:
                if dep_unit.code and dep_unit.code.strip():
                    context_parts.append(f"def {dep_unit.name} (from {dep_unit.file_path}):")
                    context_parts.append(dep_unit.code)
                    context_parts.append("") # Separator

        # 2. Class Context Injection
        # If this checks member variables, we should see __init__
        if unit.parent_name:
            # Find the __init__ of the parent class
            # We can't query by "ClassName.__init__" easily with current SymbolTable structure
            
            init_units = self.symbol_table.get_units("__init__")
            
            for init_unit in init_units:
                if (init_unit.parent_name == unit.parent_name and 
                    init_unit.file_path == unit.file_path):
                    
                    if init_unit.code not in context_parts: 
                        context_parts.insert(0, "") 
                        context_parts.insert(0, init_unit.code)
                        context_parts.insert(0, f"class {unit.parent_name} __init__ (Context):")
                    break

        if not context_parts:
            return ""

        # Construct the final formatted block
        header = "--- DEPENDENCIES (Read-Only Context) ---\n" \
                 "The following functions are CALLED by the target code.\n" \
                 "Use them to understand the cost of operations (e.g. expensive loops, busy waits).\n"
        
        footer = "--- END DEPENDENCIES ---\n"
        
        return "\n" + header + "\n".join(context_parts) + "\n" + footer
