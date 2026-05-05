package org.secretflow.scql.hive;

import java.util.Locale;

final class ServerConfig {
  String party = "alice";
  String host = "0.0.0.0";
  String advertiseHost = "localhost";
  int port = 8815;
  String backend = "duckdb";
  String hiveHost;
  int hivePort = 10000;
  String hiveUser;
  String hivePassword;
  String hiveDatabase = "default";
  boolean hiveDatabaseExplicit;
  String hiveAuth = "NONE";
  String duckdbPath;

  static ServerConfig parse(String[] args) {
    final ServerConfig config = new ServerConfig();
    for (int i = 0; i < args.length; i++) {
      final String arg = args[i];
      switch (arg) {
        case "--party":
          config.party = requireValue(args, ++i, arg);
          break;
        case "--host":
          config.host = requireValue(args, ++i, arg);
          break;
        case "--advertise-host":
          config.advertiseHost = requireValue(args, ++i, arg);
          break;
        case "--port":
          config.port = Integer.parseInt(requireValue(args, ++i, arg));
          break;
        case "--backend":
          config.backend = requireValue(args, ++i, arg).toLowerCase(Locale.ROOT);
          break;
        case "--hive-host":
          config.hiveHost = requireValue(args, ++i, arg);
          break;
        case "--hive-port":
          config.hivePort = Integer.parseInt(requireValue(args, ++i, arg));
          break;
        case "--hive-user":
          config.hiveUser = requireValue(args, ++i, arg);
          break;
        case "--hive-password":
          config.hivePassword = requireValue(args, ++i, arg);
          break;
        case "--hive-database":
          config.hiveDatabase = requireValue(args, ++i, arg);
          config.hiveDatabaseExplicit = true;
          break;
        case "--hive-auth":
          config.hiveAuth = requireValue(args, ++i, arg).toUpperCase(Locale.ROOT);
          break;
        case "--duckdb-path":
          config.duckdbPath = requireValue(args, ++i, arg);
          break;
        case "--help":
        case "-h":
          printUsageAndExit(0);
          break;
        default:
          throw new IllegalArgumentException("unknown argument: " + arg);
      }
    }

    if (!"duckdb".equals(config.backend) && !"hive".equals(config.backend)) {
      throw new IllegalArgumentException("--backend must be duckdb or hive");
    }
    if ("hive".equals(config.backend) && (config.hiveHost == null || config.hiveHost.isEmpty())) {
      throw new IllegalArgumentException("--hive-host is required when --backend hive");
    }
    if ("hive".equals(config.backend) && !config.hiveDatabaseExplicit) {
      config.hiveDatabase = config.party;
    }
    if (config.duckdbPath == null || config.duckdbPath.isEmpty()) {
      config.duckdbPath = "/tmp/scql-flight-" + config.party + ".duckdb";
    }
    return config;
  }

  private static String requireValue(String[] args, int index, String argName) {
    if (index >= args.length) {
      throw new IllegalArgumentException("missing value for " + argName);
    }
    return args[index];
  }

  private static void printUsageAndExit(int code) {
    System.out.println("Usage: java -jar scql-hive-flight-sql-server.jar [options]");
    System.out.println("  --party alice|bob");
    System.out.println("  --host 0.0.0.0");
    System.out.println("  --advertise-host localhost");
    System.out.println("  --port 8815");
    System.out.println("  --backend duckdb|hive");
    System.out.println("  --hive-host localhost");
    System.out.println("  --hive-port 10000");
    System.out.println("  --hive-user hive");
    System.out.println("  --hive-password ******");
    System.out.println("  --hive-database <default: same as --party when backend=hive>");
    System.out.println("  --hive-auth NONE|LDAP|KERBEROS");
    System.out.println("  --duckdb-path /tmp/scql-flight-alice.duckdb");
    System.exit(code);
  }
}
