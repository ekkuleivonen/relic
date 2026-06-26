package search

type ValueType string

const (
	TypeUnknown   ValueType = "unknown"
	TypeNull      ValueType = "null"
	TypeString    ValueType = "string"
	TypeInteger   ValueType = "integer"
	TypeFloat     ValueType = "float"
	TypeBoolean   ValueType = "boolean"
	TypeTimestamp ValueType = "timestamp"
)

type TargetDefinition struct {
	Target Target
	Fields []FieldDefinition
}

type FieldDefinition struct {
	Name string
	Type ValueType
}

type AttributeDefinition struct {
	Path string
	Type ValueType
}

func BuiltinAttributeDefinitions() []AttributeDefinition {
	return []AttributeDefinition{
		{Path: "upstream.size", Type: TypeInteger},
		{Path: "upstream.last_modified", Type: TypeTimestamp},
		{Path: "upstream.header.content_type", Type: TypeString},
		{Path: "upstream.s3.version_id", Type: TypeString},
		{Path: "core.first_seen_at", Type: TypeTimestamp},
		{Path: "core.last_seen_at", Type: TypeTimestamp},
		{Path: "core.object_id", Type: TypeString},
	}
}

func RegisteredAttributeDefinitions() []AttributeDefinition {
	return nil
}

func BuiltinTargetDefinitions() []TargetDefinition {
	return []TargetDefinition{
		{
			Target: TargetObjects,
			Fields: []FieldDefinition{
				{Name: "id", Type: TypeString},
				{Name: "bucket_id", Type: TypeString},
				{Name: "key", Type: TypeString},
				{Name: "created_at", Type: TypeTimestamp},
				{Name: "updated_at", Type: TypeTimestamp},
			},
		},
		{
			Target: TargetRelations,
			Fields: []FieldDefinition{
				{Name: "id", Type: TypeString},
				{Name: "source_object_id", Type: TypeString},
				{Name: "target_object_id", Type: TypeString},
				{Name: "relation_type", Type: TypeString},
				{Name: "created_at", Type: TypeTimestamp},
				{Name: "updated_at", Type: TypeTimestamp},
			},
		},
	}
}
