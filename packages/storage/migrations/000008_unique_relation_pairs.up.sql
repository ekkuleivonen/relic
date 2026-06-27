CREATE UNIQUE INDEX relations_source_target_type_idx
    ON relations (source_object_id, target_object_id, relation_type);
