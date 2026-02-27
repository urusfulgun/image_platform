#!/bin/sh

# 1. Wait for Debezium's REST API to be available
echo "Waiting for Debezium to start..."
until curl -s http://debezium:8083/connectors > /dev/null; do
  echo "Debezium API not ready yet... sleeping"
  sleep 5
done

echo "Debezium is up! Registering Keycloak connector with SMT transformations..."

# 2. Register/Update the connector using PUT (Idempotent)
curl -i -X PUT -H "Accept:application/json" -H "Content-Type:application/json" \
  http://debezium:8083/connectors/keycloak-user-sync/config \
  -d '{
  "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
  "plugin.name": "pgoutput",
  "database.hostname": "postgres-keycloak",
  "database.port": "5432",
  "database.user": "keycloak",
  "database.password": "dev-password",
  "database.dbname": "keycloak",
  "topic.prefix": "keycloak_events",
  "table.include.list": "public.user_entity",
  "slot.name": "debezium_keycloak_slot",
  
  "transforms": "unwrap,route",
  
  "transforms.unwrap.type": "io.debezium.transforms.ExtractNewRecordState",
  "transforms.unwrap.add.fields": "op",
  "transforms.unwrap.delete.handling.mode": "rewrite",
  "transforms.unwrap.drop.tombstones": "false",

  "transforms.route.type": "org.apache.kafka.connect.transforms.RegexRouter",
  "transforms.route.regex": "keycloak_events\\.public\\.(.*)",
  "transforms.route.replacement": "keycloak-users",

  "key.converter": "org.apache.kafka.connect.json.JsonConverter",
  "key.converter.schemas.enable": "false",
  "value.converter": "org.apache.kafka.connect.json.JsonConverter",
  "value.converter.schemas.enable": "false"
}'

echo "\nConnector registration completed successfully."