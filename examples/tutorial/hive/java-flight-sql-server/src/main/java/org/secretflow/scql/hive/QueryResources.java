package org.secretflow.scql.hive;

import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

final class QueryResources implements AutoCloseable {
  final Connection connection;
  final Statement statement;
  final ResultSet resultSet;

  QueryResources(Connection connection, Statement statement, ResultSet resultSet) {
    this.connection = connection;
    this.statement = statement;
    this.resultSet = resultSet;
  }

  @Override
  public void close() throws SQLException {
    try {
      resultSet.close();
    } finally {
      try {
        statement.close();
      } finally {
        connection.close();
      }
    }
  }
}
