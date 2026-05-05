package org.secretflow.scql.hive;

import java.sql.SQLException;

interface QueryBackend extends AutoCloseable {
  String preprocess(String query);

  QueryResources execute(String query) throws SQLException;

  String describe();

  @Override
  default void close() throws Exception {}
}
