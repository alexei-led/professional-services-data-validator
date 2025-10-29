# Copyright 2024 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
ClickHouse-specific patches for ibis to preserve case-sensitive SQL syntax.

ClickHouse is case-sensitive for identifiers, function names, and keywords.
This module patches ibis's ClickHouse compiler to preserve the exact SQL
without modification, preventing sqlglot from uppercasing queries.

The patches are applied automatically when this module is imported.
"""

from sqlglot import exp
from sqlglot.dialects import clickhouse
import ibis.expr.operations as ops
from ibis.backends.clickhouse.compiler import relations


def _patched_command_sql(self, expression: exp.Command) -> str:
    """
    Preserve case when rendering Command expressions for ClickHouse.

    The original sqlglot implementation uppercases the command content via
    `.upper()`, but ClickHouse identifiers are case-sensitive (e.g.,
    'mydb' != 'MYDB'). This patched version preserves the original case
    from the SQL query.

    Uses self.sql() instead of expression.text() to properly handle both
    raw text commands and programmatically constructed AST children.
    """
    # Use self.sql() for both parts to handle AST children correctly
    # and strip to maintain consistent formatting
    command_part = self.sql(expression, "this")
    expression_part = self.sql(expression, "expression").strip()
    return f"{command_part} {expression_part}" if expression_part else command_part


clickhouse.ClickHouse.Generator.command_sql = _patched_command_sql


@relations.translate_rel.register(ops.SQLQueryResult)
def _query_clickhouse_patched(op: ops.SQLQueryResult, *, aliases, **_):
    """
    Preserve exact SQL for ClickHouse queries without parsing.

    ClickHouse is case-sensitive, so we wrap all queries in Command expressions
    to preserve the original SQL exactly as written, including function names,
    identifiers, and keywords.

    Parameters
    ----------
    op : ops.SQLQueryResult
        The SQL query operation to translate
    aliases : dict
        Mapping of operations to their aliases
    **_
        Additional keyword arguments (unused)

    Returns
    -------
    sqlglot.expressions.Subquery
        A subquery expression wrapping the raw SQL query
    """
    cmd = exp.Command(this=op.query)
    return exp.Subquery(this=cmd, alias=aliases.get(op, "_"))
