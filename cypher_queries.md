# VISUALISATION

## Schema Visualisation
CALL db.schema.visualization();

## TOP REPORTING COMPANIES: Returns nodes and relationships for graph view
MATCH (c:Company)-[r:REPORTS]->(m:Metric)
WITH c, count(r) as report_count
ORDER BY report_count DESC
LIMIT 5
MATCH (c)-[r:REPORTS]->(m:Metric)
RETURN c, r, m
LIMIT 50;

## COMPANY RISK NETWORKS
MATCH (c:Company)-[r1:FACES]->(risk:Risk)
WITH c, count(r1) as risk_count
ORDER BY risk_count DESC
LIMIT 3
MATCH (c)-[r:FACES|IMPLEMENTS|PRODUCES]->(entity)
RETURN c, r, entity
LIMIT 40;

## METRIC RELATIONSHIP CHAINS: 2-hop paths as graph
MATCH path = (c:Company)-[r1:REPORTS]->(m1:Metric)-[r2:RELATED_TO]->(m2:Metric)
WITH path
LIMIT 20
UNWIND nodes(path) as n
UNWIND relationships(path) as rel
RETURN DISTINCT n, rel;

## HIGH-FREQUENCY RELATIONSHIP SUBGRAPH: Most connected entities
MATCH (c:Company)-[r:REPORTS]->(m:Metric)
WITH c, m, r, count(*) as freq
ORDER BY freq DESC
LIMIT 30
RETURN c, r, m;

## COMPANY ECOSYSTEM
MATCH (c:Company {name: 'Microsoft'})
MATCH (c)-[r]->(entity)
RETURN c, r, entity
LIMIT 50;

# STRATEGY-IMPLEMENTATION NETWORKS: Visualizable business strategy graph
MATCH (c:Company)-[r1:IMPLEMENTS]->(s:Strategy)
OPTIONAL MATCH (s)-[r2:MENTIONED_IN]->(target)
RETURN c, r1, s, r2, target
LIMIT 30;

## PRODUCT-METRIC CONNECTIONS: Product performance networks

MATCH (c:Company)-[r1:PRODUCES]->(p:Product)-[r2:RELATED_TO]->(m:Metric)
RETURN c, r1, p, r2, m
LIMIT 25;

## MENTION NETWORKS: Cross-company references
MATCH (c1:Company)-[r1:REPORTS]->(m:Metric)-[r2:MENTIONED_IN]->(c2:Company)
WHERE c1 <> c2
RETURN c1, r1, m, r2, c2
LIMIT 20;

# DETAILED INTROSPECTION

## Sample diverse relationship types with triplets
MATCH (a)-[r]->(b)
WITH type(r) as rel_type,
     collect(DISTINCT labels[a](0)) as source_labels,
     collect(DISTINCT labels[b](0)) as target_labels,
     collect[{source: a, rel: r, target: b}](0..3) as examples
RETURN
    rel_type,
    source_labels,
    target_labels,
    [ex IN examples | {
        source_label: labels[ex.source](0),
        source_props: keys[ex.source](0..2),
        rel_type: type(ex.rel),
        rel_props: keys[ex.rel](0..2),
        target_label: labels[ex.target](0),
        target_props: keys[ex.target](0..2)
    }] as sample_triplets
ORDER BY rel_type
LIMIT 20;

## More detailed triplet view with property values
MATCH (a)-[r]->(b)
WITH type(r) as relationship_type, a, r, b
ORDER BY rand()
RETURN
    labels[a](0) as source_node_type,
    [key IN keys[a](0..2) | key + ": " + toString(a[key])][0..2] as source_sample_props,
    relationship_type,
    [key IN keys[r](0..2) | key + ": " + toString(r[key])][0..2] as rel_sample_props,
    labels[b](0) as target_node_type,
    [key IN keys[b](0..2) | key + ": " + toString(b[key])][0..2] as target_sample_props
LIMIT 25;

## Manual schema extraction - relationship patterns
MATCH (a)-[r]->(b)
WITH labels(a) as source_labels, type(r) as rel_type, labels(b) as target_labels
UNWIND source_labels as source_label
UNWIND target_labels as target_label
WITH source_label, rel_type, target_label, count(*) as frequency
RETURN
    source_label + " -[:" + rel_type + "]-> " + target_label as pattern,
    frequency
ORDER BY frequency DESC;

## Node types and their properties
CALL db.labels() YIELD label
CALL {
    WITH label
    MATCH (n) WHERE label IN labels(n)
    WITH n LIMIT 100
    RETURN collect(DISTINCT keys(n)) as all_keys
}
UNWIND all_keys as key_list
UNWIND key_list as prop
WITH label, collect(DISTINCT prop) as properties
RETURN label as node_type, properties
ORDER BY node_type;

## Relationship types and their properties
CALL db.relationshipTypes() YIELD relationshipType
CALL {
    WITH relationshipType
    MATCH ()-[r]->() WHERE type(r) = relationshipType
    WITH r LIMIT 100
    RETURN collect(DISTINCT keys(r)) as all_keys
}
UNWIND all_keys as key_list
UNWIND key_list as prop
WITH relationshipType, collect(DISTINCT prop) as properties
RETURN relationshipType as relationship_type, properties
ORDER BY relationship_type;

## Comprehensive schema overview

MATCH (a)-[r]->(b)

WITH
    labels[a](0) as source_type,
    type(r) as relationship_type,
    labels[b](0) as target_type,
    count(*) as count,
    collect(DISTINCT keys(a))[0] as source_props,
    collect(DISTINCT keys(r))[0] as rel_props,
    collect(DISTINCT keys(b))[0] as target_props
RETURN
    source_type,
    source_props[0..5] as sample_source_properties,
    relationship_type,
    rel_props[0..5] as sample_rel_properties,
    target_type,
    target_props[0..5] as sample_target_properties,
    count
ORDER BY count DESC
LIMIT 20;

## Network density around high-frequency relationships
MATCH (c:Company)-[:REPORTS]->(m:Metric)
WITH c, count(m) as metric_count
WHERE metric_count > 20
MATCH subgraph = (c)-[*1..2]-(connected)
RETURN c.name as central_company,
       metric_count,
       collect(DISTINCT labels[connected](0)) as connected_types,
       size(collect(DISTINCT connected)) as network_size
ORDER BY metric_count DESC, network_size DESC

## Find most important 3-hop chains by frequency
MATCH path = (start)-[r1]->(middle)-[r2]->(end)
WHERE labels[start](0) IN ['Company']
WITH path, start, middle, end, r1, r2,
     CASE type(r1)
         WHEN 'REPORTS' THEN 100
         WHEN 'FACES' THEN 80  
         WHEN 'PRODUCES' THEN 70
         WHEN 'IMPLEMENTS' THEN 60
         ELSE 40
     END +
     CASE type(r2)
         WHEN 'RELATED_TO' THEN 50
         WHEN 'MENTIONED_IN' THEN 40
         WHEN 'IMPACTS' THEN 60
         ELSE 30
     END as importance_score
RETURN
    start.name as start_entity,
    labels[start](0) as start_type,
    type(r1) as first_relationship,
    middle.name as middle_entity,
    labels[middle](0) as middle_type,
    type(r2) as second_relationship,
    end.name as end_entity,
    labels[end](0) as end_type,
    importance_score,
    start.name + " -[" + type(r1) + "]-> " +
    middle.name + " -[" + type(r2) + "]-> " +
    end.name as full_chain
ORDER BY importance_score DESC
LIMIT 25;
