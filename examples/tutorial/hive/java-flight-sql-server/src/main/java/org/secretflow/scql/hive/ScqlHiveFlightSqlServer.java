package org.secretflow.scql.hive;

import org.apache.arrow.flight.FlightServer;
import org.apache.arrow.flight.Location;
import org.apache.arrow.memory.BufferAllocator;
import org.apache.arrow.memory.RootAllocator;

public final class ScqlHiveFlightSqlServer {
  private ScqlHiveFlightSqlServer() {}

  public static void main(String[] args) throws Exception {
    final ServerConfig config = ServerConfig.parse(args);

    try (RootAllocator rootAllocator = new RootAllocator(Long.MAX_VALUE);
        QueryBackend backend = createBackend(config)) {
      final BufferAllocator serverAllocator =
          rootAllocator.newChildAllocator("scql-hive-flight-server", 0, Long.MAX_VALUE);
      try (ScqlHiveFlightSqlProducer producer =
              new ScqlHiveFlightSqlProducer(
                  serverAllocator,
                  backend,
                  Location.forGrpcInsecure(config.advertiseHost, config.port),
                  config.party);
          FlightServer server =
              FlightServer.builder(
                      rootAllocator, Location.forGrpcInsecure(config.host, config.port), producer)
                  .build()) {
        printStartupBanner(config, backend);
        server.start();
        System.out.println("server started, press Ctrl+C to stop");
        server.awaitTermination();
      }
    }
  }

  private static QueryBackend createBackend(ServerConfig config) throws Exception {
    if ("hive".equals(config.backend)) {
      return new HiveBackend(config);
    }
    return new DuckDbBackend(config);
  }

  private static void printStartupBanner(ServerConfig config, QueryBackend backend) {
    System.out.println("============================================================");
    System.out.println("SCQL Hive Arrow Flight SQL Server (Java)");
    System.out.println("============================================================");
    System.out.println("party      : " + config.party);
    System.out.println("backend    : " + config.backend);
    System.out.println("listen     : grpc://" + config.host + ":" + config.port);
    System.out.println("advertise  : grpc://" + config.advertiseHost + ":" + config.port);
    System.out.println("jdbc       : " + backend.describe());
    System.out.println("------------------------------------------------------------");
  }
}
