"""Tests for ClickHouse ibis backend patches.

Verifies that ClickHouse queries preserve exact SQL including case-sensitive
identifiers and function names, since ClickHouse is case-sensitive.

Following DVT's testing patterns:
- Test patch registration (verify monkey-patch applied)
- Test handler function behavior directly with minimal mocks
- Focus on testing OUR code, not ibis framework
"""

from unittest import mock

import pytest


def get_module_under_test():
    """Attempt to import the ClickHouse ibis module."""
    try:
        from third_party.ibis import ibis_clickhouse
    except ModuleNotFoundError:
        # We don't necessarily have the ClickHouse driver installed.
        # Tests will be skipped when the driver is missing.
        ibis_clickhouse = None

    return ibis_clickhouse


@pytest.fixture
def module_under_test():
    """Fixture providing the ClickHouse ibis module."""
    return get_module_under_test()


@pytest.mark.skipif(not get_module_under_test(), reason="No ClickHouse driver")
def test_import(module_under_test):
    """Test that the ClickHouse ibis module can be imported."""
    assert module_under_test is not None


@pytest.mark.skipif(not get_module_under_test(), reason="No ClickHouse driver")
def test_clickhouse_patch_registered(module_under_test):
    """Test that the ClickHouse translate_rel patch is registered."""
    import ibis.expr.operations as ops
    from ibis.backends.clickhouse.compiler import relations

    # Verify that ops.SQLQueryResult has a custom handler registered
    assert ops.SQLQueryResult in relations.translate_rel.registry

    # Get the registered function
    handler = relations.translate_rel.registry[ops.SQLQueryResult]

    # Verify it's our patched version that preserves case for all queries
    assert handler.__name__ == "_query_clickhouse_patched"


@pytest.mark.skipif(not get_module_under_test(), reason="No ClickHouse driver")
def test_all_queries_use_command_wrapper(module_under_test):
    """Test that all queries use Command wrapper to preserve exact SQL."""
    from sqlglot import exp

    handler = module_under_test._query_clickhouse_patched

    # Test with various query types - all should use Command
    queries = [
        "SELECT col1, col2 FROM table1 WHERE col1 > 10",
        "SELECT col1, item FROM table1 ARRAY JOIN array_col AS item",
        "SELECT * FROM table1 FINAL WHERE date = today()",
        "SELECT t1.id FROM table1 t1 GLOBAL JOIN table2 t2 ON t1.id = t2.id",
    ]

    for query in queries:
        mock_op = mock.Mock()
        mock_op.query = query
        result = handler(mock_op, aliases={mock_op: "_"})

        # All queries should return Subquery with Command (no parsing)
        assert isinstance(result, exp.Subquery)
        assert isinstance(result.this, exp.Command)


@pytest.mark.skipif(not get_module_under_test(), reason="No ClickHouse driver")
def test_command_sql_patch_applied(module_under_test):
    """Test that the command_sql patch is applied and preserves case."""
    from sqlglot import exp
    from sqlglot.dialects import clickhouse

    # Verify the patch is applied
    assert hasattr(clickhouse.ClickHouse.Generator, "command_sql")

    # Verify the patched function actually preserves case by rendering a command
    generator = clickhouse.ClickHouse.Generator()
    cmd = exp.Command(this="SELECT * FROM testDb.testTable")
    result = generator.command_sql(cmd)

    # The patched version should preserve case (not uppercase everything)
    assert "testDb.testTable" in result
    assert "TESTDB.TESTTABLE" not in result


@pytest.mark.skipif(not get_module_under_test(), reason="No ClickHouse driver")
def test_lowercase_identifiers_preserved(module_under_test):
    """Test that lowercase identifiers are preserved in ARRAY JOIN queries.

    ClickHouse identifiers are case-sensitive, so 'mydb.mytable' != 'MYDB.MYTABLE'.
    This test verifies that our patch preserves the original case.
    """

    handler = module_under_test._query_clickhouse_patched

    # Use lowercase database and table names
    mock_op = mock.Mock()
    mock_op.query = """
        SELECT T.project_id, item_value
        FROM testdb.testtable AS T
        ARRAY JOIN T.items AS item_value
        WHERE T.project_id = 'test'
    """

    aliases = {mock_op: "_"}
    result = handler(mock_op, aliases=aliases)

    # Generate SQL
    result_sql = result.sql(dialect="clickhouse")

    # Verify lowercase identifiers are preserved (not uppercased)
    assert "testdb.testtable" in result_sql
    assert "TESTDB.TESTTABLE" not in result_sql


@pytest.mark.skipif(not get_module_under_test(), reason="No ClickHouse driver")
def test_mixed_case_identifiers_preserved(module_under_test):
    """Test that mixed-case identifiers are preserved in ARRAY JOIN queries."""

    handler = module_under_test._query_clickhouse_patched

    # Use mixed-case database and table names
    mock_op = mock.Mock()
    mock_op.query = """
        SELECT T.userId, event_item
        FROM myDatabase.myTable AS T
        ARRAY JOIN T.events AS event_item
        WHERE T.userId > 100
    """

    aliases = {mock_op: "_"}
    result = handler(mock_op, aliases=aliases)

    # Generate SQL
    result_sql = result.sql(dialect="clickhouse")

    # Verify mixed-case identifiers are preserved
    assert "myDatabase.myTable" in result_sql
    assert "MYDATABASE.MYTABLE" not in result_sql


@pytest.mark.skipif(not get_module_under_test(), reason="No ClickHouse driver")
def test_case_sensitivity_with_final_modifier(module_under_test):
    """Test that case is preserved with FINAL modifier."""

    handler = module_under_test._query_clickhouse_patched

    mock_op = mock.Mock()
    mock_op.query = "SELECT * FROM analyticsDB.events FINAL WHERE date = today()"

    aliases = {mock_op: "_"}
    result = handler(mock_op, aliases=aliases)

    result_sql = result.sql(dialect="clickhouse")

    # Verify case preservation
    assert "analyticsDB.events" in result_sql
    assert "ANALYTICSDB.EVENTS" not in result_sql


@pytest.mark.skipif(not get_module_under_test(), reason="No ClickHouse driver")
def test_function_names_case_preserved(module_under_test):
    """Test that lowercase function names are preserved (not uppercased).

    ClickHouse functions are case-sensitive: any() exists but ANY() does not.
    This test verifies the fix for the issue where DVT was uppercasing
    function names, causing queries to fail in ClickHouse.
    """

    handler = module_under_test._query_clickhouse_patched

    # Test various ClickHouse functions with their correct lowercase names
    mock_op = mock.Mock()
    mock_op.query = """
        SELECT
            any(service_description) AS service,
            sum(cost) AS total_cost,
            arraySum(arr_col) AS arr_total,
            toDateTime(timestamp) AS dt
        FROM table1
        GROUP BY project_id
    """

    aliases = {mock_op: "_"}
    result = handler(mock_op, aliases=aliases)

    result_sql = result.sql(dialect="clickhouse")

    # Verify lowercase function names are preserved (not uppercased)
    assert "any(service_description)" in result_sql
    assert "sum(cost)" in result_sql
    assert "arraySum(arr_col)" in result_sql
    assert "toDateTime(timestamp)" in result_sql

    # Verify they were NOT uppercased
    assert "ANY(service_description)" not in result_sql
    assert "SUM(cost)" not in result_sql
    assert "ARRAYSUM(arr_col)" not in result_sql
    assert "TODATETIME(timestamp)" not in result_sql
