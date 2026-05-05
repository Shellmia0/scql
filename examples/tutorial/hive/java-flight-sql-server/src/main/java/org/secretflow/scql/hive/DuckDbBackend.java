package org.secretflow.scql.hive;

import java.io.File;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

final class DuckDbBackend implements QueryBackend {
  private final String jdbcUrl;
  private final String party;
  private final HiveDialectConverter converter;

  DuckDbBackend(ServerConfig config) throws Exception {
    Class.forName("org.duckdb.DuckDBDriver");
    this.jdbcUrl = "jdbc:duckdb:" + config.duckdbPath;
    this.party = config.party;
    this.converter = new HiveDialectConverter(config.party, "default");
    initialize();
  }

  @Override
  public String preprocess(String query) {
    return converter.convert(query);
  }

  @Override
  public QueryResources execute(String query) throws SQLException {
    final Connection connection = DriverManager.getConnection(jdbcUrl);
    final Statement statement = connection.createStatement();
    statement.execute("CREATE SCHEMA IF NOT EXISTS \"default\"");
    statement.execute("SET search_path TO \"default\"");
    final ResultSet resultSet = statement.executeQuery(query);
    return new QueryResources(connection, statement, resultSet);
  }

  @Override
  public String describe() {
    return jdbcUrl;
  }

  private void initialize() throws SQLException {
    final File file = new File(jdbcUrl.substring("jdbc:duckdb:".length()));
    final File parent = file.getParentFile();
    if (parent != null) {
      parent.mkdirs();
    }
    try (Connection connection = DriverManager.getConnection(jdbcUrl);
        Statement statement = connection.createStatement()) {
      statement.execute("CREATE SCHEMA IF NOT EXISTS \"default\"");
      statement.execute("SET search_path TO \"default\"");
      if ("alice".equalsIgnoreCase(party)) {
        statement.execute(
            "CREATE TABLE IF NOT EXISTS user_credit (ID VARCHAR, credit_rank INTEGER, income INTEGER, age INTEGER)");
        if (tableCount(statement, "user_credit") == 0) {
          statement.execute(
              "INSERT INTO user_credit VALUES "
                  + "('id0001', 6, 100000, 20),"
                  + "('id0002', 5, 90000, 19),"
                  + "('id0003', 6, 89700, 32),"
                  + "('id0005', 6, 607000, 30),"
                  + "('id0006', 5, 30070, 25),"
                  + "('id0007', 6, 12070, 28),"
                  + "('id0008', 6, 200800, 50),"
                  + "('id0009', 6, 607000, 30),"
                  + "('id0010', 5, 30070, 25),"
                  + "('id0011', 5, 12070, 28),"
                  + "('id0012', 6, 200800, 50),"
                  + "('id0013', 5, 30070, 25),"
                  + "('id0014', 5, 12070, 28),"
                  + "('id0015', 6, 200800, 18),"
                  + "('id0016', 5, 30070, 26),"
                  + "('id0017', 5, 12070, 27),"
                  + "('id0018', 6, 200800, 16),"
                  + "('id0019', 6, 30070, 25),"
                  + "('id0020', 5, 12070, 28)");
        }
      } else {
        statement.execute(
            "CREATE TABLE IF NOT EXISTS user_stats (ID VARCHAR, order_amount INTEGER, is_active INTEGER)");
        if (tableCount(statement, "user_stats") == 0) {
          statement.execute(
              "INSERT INTO user_stats VALUES "
                  + "('id0001', 5000, 1),"
                  + "('id0002', 3000, 1),"
                  + "('id0003', 8000, 0),"
                  + "('id0005', 12000, 1),"
                  + "('id0006', 1500, 1),"
                  + "('id0007', 2500, 0),"
                  + "('id0008', 9500, 1),"
                  + "('id0009', 7000, 1),"
                  + "('id0010', 500, 0),"
                  + "('id0011', 3500, 1),"
                  + "('id0012', 15000, 1),"
                  + "('id0013', 2000, 0),"
                  + "('id0014', 4500, 1),"
                  + "('id0015', 6500, 1),"
                  + "('id0016', 1000, 0),"
                  + "('id0017', 8500, 1),"
                  + "('id0018', 11000, 1),"
                  + "('id0019', 3200, 1),"
                  + "('id0020', 7500, 0)");
        }
      }
    }
  }

  private static int tableCount(Statement statement, String tableName) throws SQLException {
    try (ResultSet rs = statement.executeQuery("SELECT COUNT(*) FROM " + tableName)) {
      rs.next();
      return rs.getInt(1);
    }
  }
}
