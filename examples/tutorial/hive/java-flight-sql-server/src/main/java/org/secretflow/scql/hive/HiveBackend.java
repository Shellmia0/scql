package org.secretflow.scql.hive;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.Properties;

final class HiveBackend implements QueryBackend {
  private final String jdbcUrl;
  private final Properties properties = new Properties();
  private final HiveDialectConverter converter;

  HiveBackend(ServerConfig config) throws Exception {
    Class.forName("org.apache.hive.jdbc.HiveDriver");
    this.jdbcUrl = buildJdbcUrl(config);
    if (config.hiveUser != null && !config.hiveUser.isEmpty()) {
      properties.setProperty("user", config.hiveUser);
    }
    if (config.hivePassword != null && !config.hivePassword.isEmpty()) {
      properties.setProperty("password", config.hivePassword);
    }
    this.converter = new HiveDialectConverter(config.party, config.hiveDatabase);
  }

  @Override
  public String preprocess(String query) {
    return converter.convert(query);
  }

  @Override
  public QueryResources execute(String query) throws SQLException {
    final Connection connection = DriverManager.getConnection(jdbcUrl, properties);
    final Statement statement = connection.createStatement();
    statement.setFetchSize(1024);
    final ResultSet resultSet = statement.executeQuery(query);
    return new QueryResources(connection, statement, resultSet);
  }

  @Override
  public String describe() {
    return jdbcUrl;
  }

  private static String buildJdbcUrl(ServerConfig config) {
    final StringBuilder sb =
        new StringBuilder()
            .append("jdbc:hive2://")
            .append(config.hiveHost)
            .append(":")
            .append(config.hivePort)
            .append("/")
            .append(config.hiveDatabase);
    if (!"NONE".equals(config.hiveAuth)) {
      sb.append(";auth=").append(config.hiveAuth);
    }
    return sb.toString();
  }
}
