"""Universal parser using configuration-driven Tree-sitter mappings.

Replaces language-specific parsers with a generic engine that can handle
any language defined in `axon.config.languages`.
"""

from __future__ import annotations

from typing import Any

from tree_sitter import Node, Parser

from axon.config.languages import LanguageConfig
from axon.core.parsers.base import (
    AstNodeInfo,
    CallInfo,
    ImportInfo,
    LanguageParser,
    ParseResult,
    SymbolInfo,
    TypeRef,
)


class UniversalParser(LanguageParser):
    """Generic parser that uses LanguageConfig to walk the AST."""

    def __init__(self, config: LanguageConfig) -> None:
        self.config = config
        self._parser = Parser(config.get_language())
        self.mappings = config.mappings

    def parse(self, content: str, file_path: str) -> ParseResult:
        """Parse source code using the configured language grammar."""
        tree = self._parser.parse(bytes(content, "utf8"))
        result = ParseResult()
        root = tree.root_node
        
        # Initial walk for definitions
        self._walk(root, content, result, class_name="")
        
        # Separate pass for calls to handle scoping correctly (simplified for universal)
        self._extract_calls_recursive(root, result)
        
        return result

    def _walk(
        self,
        node: Node,
        content: str,
        result: ParseResult,
        class_name: str,
    ) -> None:
        """Recursively walk the AST to extract definitions."""
        # Check against mappings
        node_type = node.type
        
        if node_type in self.mappings.function:
            self._extract_function(node, content, result, class_name)
        elif node_type in self.mappings.class_def:
            self._extract_class(node, content, result)
        elif node_type in self.mappings.method:
            # If method is distinct from function (like in JS/TS)
            self._extract_function(node, content, result, class_name)
        elif node_type in self.mappings.import_stmt:
            self._extract_import(node, result)
        elif node_type in self.mappings.variable_decl:
            # Add to AST nodes
            result.ast_nodes.append(self._extract_recursive_ast(node, content))
        elif node_type in self.mappings.control_flow or node_type in self.mappings.block:
            # Add to AST nodes
            result.ast_nodes.append(self._extract_recursive_ast(node, content))
            # Also recurse to find nested definitions (e.g. function inside if)
            for child in node.children:
                self._walk(child, content, result, class_name)
            return # _walk recursion is handled above, so return to avoid double recursion if I didn't break
        elif node_type in self.mappings.interface:
             self._extract_interface(node, content, result)
        elif node_type in self.mappings.type_alias:
             self._extract_type_alias(node, content, result)
        else:
            # Continue recursion
            for child in node.children:
                self._walk(child, content, result, class_name)

    def _extract_recursive_ast(self, node: Node, content: str) -> AstNodeInfo:
        """Build a tree of AstNodeInfo for structural analysis."""
        children = []
        for child in node.children:
            # We recurse if the child is also a block/flow/var/call
            # Or just capture everything? "Proper AST" implies everything.
            # But that's huge. Let's capture structure.
            if child.type in self.mappings.block or \
               child.type in self.mappings.control_flow or \
               child.type in self.mappings.variable_decl or \
               child.type in self.mappings.call:
                children.append(self._extract_recursive_ast(child, content))
        
        return AstNodeInfo(
            kind=node.type,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            content=content[node.start_byte : node.end_byte],
            children=children
        )

    def _extract_function(
        self,
        node: Node,
        content: str,
        result: ParseResult,
        class_name: str,
    ) -> None:
        """Extract a function/method definition."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            # Fallback: look for first identifier child
            for child in node.children:
                if child.type in self.mappings.identifier:
                    name_node = child
                    break
        
        if not name_node:
            return

        name = content[name_node.start_byte : name_node.end_byte]
        
        # Determine kind
        kind = "method" if class_name else "function"
        
        # Helper to get signature (simplified)
        params_node = node.child_by_field_name("parameters") or node.child_by_field_name("parameter_list")
        signature = ""
        if params_node:
            signature = content[params_node.start_byte : params_node.end_byte]

        symbol = SymbolInfo(
            name=name,
            kind=kind,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            content=content[node.start_byte : node.end_byte],
            signature=signature,
            class_name=class_name,
        )
        result.symbols.append(symbol)

        # Recurse into body, but update class_name if this is a class (not applicable here)
        # If this function contains other definitions (e.g. inner functions), we recurse
        body_node = node.child_by_field_name("body")
        if body_node:
            for child in body_node.children:
                self._walk(child, content, result, class_name)

    def _extract_class(
        self,
        node: Node,
        content: str,
        result: ParseResult,
    ) -> None:
        """Extract a class definition."""
        name_node = node.child_by_field_name("name")
        if not name_node:
             for child in node.children:
                if child.type in self.mappings.identifier:
                    name_node = child
                    break
        
        if not name_node:
            return

        name = content[name_node.start_byte : name_node.end_byte]
        
        symbol = SymbolInfo(
            name=name,
            kind="class",
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            content=content[node.start_byte : node.end_byte],
            signature="",
            class_name="",
        )
        result.symbols.append(symbol)

        # Recurse into body with class context
        body_node = node.child_by_field_name("body")
        if body_node:
            for child in body_node.children:
                self._walk(child, content, result, class_name=name)
        else:
            # Some languages like C++ might not have a "body" field but just children block
            for child in node.children:
                 if child.type in self.mappings.block:
                     for subchild in child.children:
                         self._walk(subchild, content, result, class_name=name)

    def _extract_interface(self, node: Node, content: str, result: ParseResult) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node: return
        name = content[name_node.start_byte : name_node.end_byte]
        
        result.symbols.append(SymbolInfo(
            name=name,
            kind="interface",
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            content=content[node.start_byte : node.end_byte],
        ))

    def _extract_type_alias(self, node: Node, content: str, result: ParseResult) -> None:
        name_node = node.child_by_field_name("name")
        if not name_node: return
        name = content[name_node.start_byte : name_node.end_byte]
        
        result.symbols.append(SymbolInfo(
            name=name,
            kind="type_alias",
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            content=content[node.start_byte : node.end_byte],
        ))

    def _extract_import(self, node: Node, result: ParseResult) -> None:
        # Import extraction is highly language specific.
        # We try to grab the module name if possible.
        # This is a best-effort fallback for the Universal Parser.
        # Python/TS have specific structures.
        # We can implement generic logic: look for string literals or identifiers inside.
        pass

    def _extract_calls_recursive(self, node: Node, result: ParseResult) -> None:
        if node.type in self.mappings.call:
            # Try to find the function name
            # Usually the first child or "function" field
            func_node = node.child_by_field_name("function")
            if not func_node:
                # TS: call_expression -> function
                # Python: call -> function
                # Fallback to first child
                if node.child_count > 0:
                    func_node = node.children[0]
            
            if func_node:
                # If it's an attribute access (obj.method), get the method name
                if func_node.type == "attribute" or func_node.type == "member_expression":
                     prop = func_node.child_by_field_name("attribute") or func_node.child_by_field_name("property")
                     if prop:
                         name = prop.text.decode("utf8")
                         # receiver = func_node.child_by_field_name("object").text...
                         # For now just name
                         result.calls.append(CallInfo(name=name, line=node.start_point[0] + 1))
                elif func_node.type in self.mappings.identifier:
                    name = func_node.text.decode("utf8")
                    result.calls.append(CallInfo(name=name, line=node.start_point[0] + 1))
        
        for child in node.children:
            self._extract_calls_recursive(child, result)
