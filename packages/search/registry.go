package search

type Registry interface {
	ResolveTarget(Target) (TargetDefinition, bool)
	ResolveField(Target, string) (FieldDefinition, bool)
	ResolveAttribute(string) (AttributeDefinition, bool)
}

type StaticRegistry struct {
	targets    map[Target]TargetDefinition
	fields     map[Target]map[string]FieldDefinition
	attributes map[string]AttributeDefinition
}

func BuiltinRegistry() *StaticRegistry {
	return NewStaticRegistry(BuiltinTargetDefinitions(), BuiltinAttributeDefinitions())
}

func NewStaticRegistry(targets []TargetDefinition, attributes []AttributeDefinition) *StaticRegistry {
	registry := &StaticRegistry{
		targets:    map[Target]TargetDefinition{},
		fields:     map[Target]map[string]FieldDefinition{},
		attributes: map[string]AttributeDefinition{},
	}

	for _, target := range targets {
		registry.targets[target.Target] = target
		registry.fields[target.Target] = map[string]FieldDefinition{}
		for _, field := range target.Fields {
			registry.fields[target.Target][field.Name] = field
		}
	}
	for _, attribute := range attributes {
		registry.attributes[attribute.Path] = attribute
	}

	return registry
}

func (r *StaticRegistry) ResolveTarget(target Target) (TargetDefinition, bool) {
	definition, ok := r.targets[target]
	return definition, ok
}

func (r *StaticRegistry) ResolveField(target Target, name string) (FieldDefinition, bool) {
	fields, ok := r.fields[target]
	if !ok {
		return FieldDefinition{}, false
	}

	definition, ok := fields[name]
	return definition, ok
}

func (r *StaticRegistry) ResolveAttribute(path string) (AttributeDefinition, bool) {
	definition, ok := r.attributes[path]
	return definition, ok
}
