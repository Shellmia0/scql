package org.secretflow.scql.hive;

import static com.google.protobuf.Any.pack;
import static org.apache.arrow.adapter.jdbc.JdbcToArrow.sqlToArrowVectorIterator;
import static org.apache.arrow.adapter.jdbc.JdbcToArrowUtils.jdbcToArrowSchema;

import com.google.protobuf.ByteString;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Calendar;
import java.util.Collections;
import org.apache.arrow.adapter.jdbc.ArrowVectorIterator;
import org.apache.arrow.adapter.jdbc.JdbcToArrowUtils;
import org.apache.arrow.flight.CallStatus;
import org.apache.arrow.flight.Criteria;
import org.apache.arrow.flight.FlightDescriptor;
import org.apache.arrow.flight.FlightEndpoint;
import org.apache.arrow.flight.FlightInfo;
import org.apache.arrow.flight.FlightProducer;
import org.apache.arrow.flight.Location;
import org.apache.arrow.flight.SchemaResult;
import org.apache.arrow.flight.Ticket;
import org.apache.arrow.flight.sql.NoOpFlightSqlProducer;
import org.apache.arrow.flight.sql.impl.FlightSql.CommandStatementQuery;
import org.apache.arrow.flight.sql.impl.FlightSql.TicketStatementQuery;
import org.apache.arrow.memory.BufferAllocator;
import org.apache.arrow.vector.VectorLoader;
import org.apache.arrow.vector.VectorSchemaRoot;
import org.apache.arrow.vector.VectorUnloader;
import org.apache.arrow.vector.types.pojo.Schema;

final class ScqlHiveFlightSqlProducer extends NoOpFlightSqlProducer {
  private static final Calendar UTC_CALENDAR = JdbcToArrowUtils.getUtcCalendar();

  private final BufferAllocator allocator;
  private final QueryBackend backend;
  private final Location endpointLocation;
  private final String party;

  ScqlHiveFlightSqlProducer(
      BufferAllocator allocator, QueryBackend backend, Location endpointLocation, String party) {
    this.allocator = allocator;
    this.backend = backend;
    this.endpointLocation = endpointLocation;
    this.party = party;
  }

  @Override
  public FlightInfo getFlightInfoStatement(
      CommandStatementQuery command, CallContext context, FlightDescriptor descriptor) {
    final String query = backend.preprocess(command.getQuery());
    log("GetFlightInfo", query);

    try (QueryResources resources = backend.execute(query)) {
      final Schema schema = jdbcToArrowSchema(resources.resultSet.getMetaData(), UTC_CALENDAR);
      final TicketStatementQuery ticket =
          TicketStatementQuery.newBuilder()
              .setStatementHandle(ByteString.copyFromUtf8(query))
              .build();
      return new FlightInfo(
          schema,
          descriptor,
          Collections.singletonList(new FlightEndpoint(new Ticket(pack(ticket).toByteArray()), endpointLocation)),
          -1,
          -1);
    } catch (SQLException e) {
      throw CallStatus.INTERNAL
          .withDescription("failed to get FlightInfo for query")
          .withCause(e)
          .toRuntimeException();
    }
  }

  @Override
  public SchemaResult getSchemaStatement(
      CommandStatementQuery command, CallContext context, FlightDescriptor descriptor) {
    final String query = backend.preprocess(command.getQuery());

    try (QueryResources resources = backend.execute(query)) {
      return new SchemaResult(jdbcToArrowSchema(resources.resultSet.getMetaData(), UTC_CALENDAR));
    } catch (SQLException e) {
      throw CallStatus.INTERNAL
          .withDescription("failed to get query schema")
          .withCause(e)
          .toRuntimeException();
    }
  }

  @Override
  public void getStreamStatement(
      TicketStatementQuery ticket, CallContext context, FlightProducer.ServerStreamListener listener) {
    final String query = backend.preprocess(ticket.getStatementHandle().toStringUtf8());
    log("DoGet", query);

    try (QueryResources resources = backend.execute(query)) {
      final ResultSet resultSet = resources.resultSet;
      final Schema schema = jdbcToArrowSchema(resultSet.getMetaData(), UTC_CALENDAR);
      try (VectorSchemaRoot root = VectorSchemaRoot.create(schema, allocator)) {
        final VectorLoader loader = new VectorLoader(root);
        listener.start(root);

        final ArrowVectorIterator iterator = sqlToArrowVectorIterator(resultSet, allocator);
        boolean wroteBatch = false;
        try {
          while (iterator.hasNext()) {
            final VectorSchemaRoot batch = iterator.next();
            if (batch.getRowCount() == 0) {
              continue;
            }
            final VectorUnloader unloader = new VectorUnloader(batch);
            loader.load(unloader.getRecordBatch());
            listener.putNext();
            root.clear();
            wroteBatch = true;
          }
        } finally {
          iterator.close();
        }

        if (!wroteBatch) {
          listener.putNext();
        }
        listener.completed();
      }
    } catch (Exception e) {
      listener.error(
          CallStatus.INTERNAL
              .withDescription("failed to stream query result")
              .withCause(e)
              .toRuntimeException());
    }
  }

  @Override
  public void listFlights(
      CallContext context, Criteria criteria, StreamListener<FlightInfo> listener) {
    listener.onError(CallStatus.UNIMPLEMENTED.withDescription("listFlights is not implemented").toRuntimeException());
  }

  @Override
  public void close() throws Exception {
    allocator.close();
  }

  private void log(String phase, String query) {
    final String compact = query.replaceAll("\\s+", " ").trim();
    System.out.println("[" + party + "] " + phase + " - " + compact);
  }
}
