"""Language configuration and detection.

Defines the capabilities and Tree-sitter mappings for supported languages.
Allows adding new languages via configuration without changing code.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tree_sitter

@dataclass
class NodeMappings:
    """Maps generic Axon concepts to language-specific Tree-sitter node types."""

    function: list[str] = field(default_factory=list)
    class_def: list[str] = field(default_factory=list)  # "class" is reserved
    method: list[str] = field(default_factory=list)
    interface: list[str] = field(default_factory=list)
    type_alias: list[str] = field(default_factory=list)
    import_stmt: list[str] = field(default_factory=list)
    call: list[str] = field(default_factory=list)
    # New AST/CPG concepts
    block: list[str] = field(default_factory=list)
    control_flow: list[str] = field(default_factory=list)  # if, for, while
    variable_decl: list[str] = field(default_factory=list)
    identifier: list[str] = field(default_factory=list)

@dataclass
class LanguageConfig:
    """Configuration for a supported language."""

    name: str
    grammar_name: str  # e.g. "tree_sitter_python" or just "python" if using bindings
    extensions: list[str]
    mappings: NodeMappings
    
    # Optional: Package name if different from "tree_sitter_{name}"
    package_name: str | None = None

    def get_language(self) -> tree_sitter.Language:
        """Dynamically load the Tree-sitter language object."""
        pkg_name = self.package_name or f"tree_sitter_{self.grammar_name}"
        try:
            module = importlib.import_module(pkg_name)
            # Standard tree-sitter bindings expose a `language()` function
            if hasattr(module, "language"):
                return tree_sitter.Language(module.language())
            # Some might expose it differently, handle as needed
            raise ImportError(f"Module {pkg_name} does not expose 'language()'")
        except ImportError as e:
            raise RuntimeError(
                f"Could not load language '{self.name}'. "
                f"Ensure '{pkg_name}' is installed."
            ) from e

# Default configurations for supported languages
PYTHON_CONFIG = LanguageConfig(
    name="python",
    grammar_name="python",
    extensions=[".py", ".pyi"],
    mappings=NodeMappings(
        function=["function_definition"],
        class_def=["class_definition"],
        method=[],  # Python methods are just function_defs inside classes
        import_stmt=["import_statement", "import_from_statement"],
        call=["call"],
        block=["block"],
        control_flow=["if_statement", "for_statement", "while_statement", "try_statement"],
        variable_decl=["assignment", "ann_assignment"],  # Approximate
        identifier=["identifier"],
    ),
)

TYPESCRIPT_CONFIG = LanguageConfig(
    name="typescript",
    grammar_name="typescript",
    extensions=[".ts", ".tsx"],
    mappings=NodeMappings(
        function=["function_declaration", "generator_function", "arrow_function"],
        class_def=["class_declaration", "abstract_class_declaration"],
        method=["method_definition"],
        interface=["interface_declaration"],
        type_alias=["type_alias_declaration"],
        import_stmt=["import_statement", "import_require_statement"],
        call=["call_expression", "new_expression"],
        block=["statement_block"],
        control_flow=["if_statement", "for_statement", "while_statement", "switch_statement"],
        variable_decl=["variable_declarator"],
        identifier=["identifier"],
    ),
)

JAVASCRIPT_CONFIG = LanguageConfig(
    name="javascript",
    grammar_name="javascript",
    extensions=[".js", ".jsx", ".mjs", ".cjs"],
    mappings=NodeMappings(
        function=["function_declaration", "generator_function", "arrow_function"],
        class_def=["class_declaration"],
        method=["method_definition"],
        import_stmt=["import_statement", "require_call"], # require() is a call, handled specially?
        call=["call_expression", "new_expression"],
        block=["statement_block"],
        control_flow=["if_statement", "for_statement", "while_statement", "switch_statement"],
        variable_decl=["variable_declarator"],
        identifier=["identifier"],
    ),
)

GO_CONFIG = LanguageConfig(
    name="go",
    grammar_name="go",
    extensions=[".go"],
    mappings=NodeMappings(
        function=["function_declaration", "method_declaration"],
        class_def=["type_declaration"],  # structs/interfaces
        method=["method_declaration"],
        interface=["type_declaration"], # distinct in Go?
        import_stmt=["import_declaration"],
        call=["call_expression"],
        block=["block"],
        control_flow=["if_statement", "for_statement", "expression_switch_statement"],
        variable_decl=["short_var_declaration", "var_declaration"],
        identifier=["identifier"],
    ),
)

RUST_CONFIG = LanguageConfig(
    name="rust",
    grammar_name="rust",
    extensions=[".rs"],
    mappings=NodeMappings(
        function=["function_item"],
        class_def=["struct_item", "enum_item", "union_item"],
        method=["function_item"], # Inside impl
        interface=["trait_item"],
        import_stmt=["use_declaration"],
        call=["call_expression"],
        block=["block"],
        control_flow=["if_expression", "loop_expression", "while_expression", "for_expression", "match_expression"],
        variable_decl=["let_declaration"],
        identifier=["identifier"],
    ),
)

JAVA_CONFIG = LanguageConfig(
    name="java",
    grammar_name="java",
    extensions=[".java"],
    mappings=NodeMappings(
        function=["method_declaration"],
        class_def=["class_declaration", "record_declaration"],
        method=["method_declaration"],
        interface=["interface_declaration"],
        import_stmt=["import_declaration"],
        call=["method_invocation"],
        block=["block"],
        control_flow=["if_statement", "while_statement", "for_statement", "enhanced_for_statement", "switch_expression"],
        variable_decl=["local_variable_declaration"],
        identifier=["identifier"],
    ),
)

CPP_CONFIG = LanguageConfig(
    name="cpp",
    grammar_name="cpp",
    extensions=[".cpp", ".cxx", ".cc", ".hpp", ".h"],
    mappings=NodeMappings(
        function=["function_definition"],
        class_def=["class_specifier", "struct_specifier"],
        method=["function_definition"],
        import_stmt=["preproc_include"],
        call=["call_expression"],
        block=["compound_statement"],
        control_flow=["if_statement", "for_statement", "while_statement", "switch_statement"],
        variable_decl=["declaration"],
        identifier=["identifier", "field_identifier"],
    ),
)

# Registry
LANGUAGES: dict[str, LanguageConfig] = {
    "python": PYTHON_CONFIG,
    "typescript": TYPESCRIPT_CONFIG,
    "javascript": JAVASCRIPT_CONFIG,
    "go": GO_CONFIG,
    "rust": RUST_CONFIG,
    "java": JAVA_CONFIG,
    "cpp": CPP_CONFIG,
}

# Extension map
EXTENSION_MAP: dict[str, str] = {}
for lang in LANGUAGES.values():
    for ext in lang.extensions:
        EXTENSION_MAP[ext] = lang.name

SUPPORTED_EXTENSIONS = EXTENSION_MAP


def get_language(file_path: str | Path) -> str | None:
    """Return the language name for *file_path*, or ``None`` if unsupported."""
    suffix = Path(file_path).suffix
    return EXTENSION_MAP.get(suffix)

def get_language_config(file_path: str | Path) -> LanguageConfig | None:
    """Return the configuration for the file's language."""
    lang_name = get_language(file_path)
    return LANGUAGES.get(lang_name) if lang_name else None

def is_supported(file_path: str | Path) -> bool:
    """Return True if the file extension is supported."""
    return Path(file_path).suffix in EXTENSION_MAP
