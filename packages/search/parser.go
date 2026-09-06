package search

import (
	"fmt"
	"strconv"
	"strings"
	"time"
	"unicode"
)

const MaxQueryBytes = 16 * 1024
const maxExpressionDepth = 64

func Parse(input string) (Query, error) {
	if len(input) > MaxQueryBytes {
		return Query{}, fmt.Errorf("query exceeds %d bytes", MaxQueryBytes)
	}
	tokens, err := lex(input)
	if err != nil {
		return Query{}, err
	}

	parser := queryParser{tokens: tokens}
	query, err := parser.parseQuery()
	if err != nil {
		return Query{}, err
	}
	if !parser.at(tokenEOF) {
		return Query{}, parser.errorf("unexpected token %q", parser.current().literal)
	}

	return query, nil
}

type queryParser struct {
	tokens []token
	pos    int
	depth  int
}

func (p *queryParser) parseQuery() (Query, error) {
	if !p.consumeKeyword("FROM") {
		return Query{}, p.errorf("query must start with FROM")
	}

	target, err := p.parseTarget()
	if err != nil {
		return Query{}, err
	}

	query := Query{
		Version: VersionV1,
		From:    target,
	}

	if p.consumeKeyword("WHERE") {
		where, err := p.parseBoolExpr()
		if err != nil {
			return Query{}, err
		}
		query.Where = where
	}

	if p.consumeKeyword("ORDER") {
		if !p.consumeKeyword("BY") {
			return Query{}, p.errorf("expected BY after ORDER")
		}
		orderBy, err := p.parseOrderBy()
		if err != nil {
			return Query{}, err
		}
		query.OrderBy = orderBy
	}

	if p.consumeKeyword("LIMIT") {
		limit, err := p.parseNonNegativeInt("LIMIT")
		if err != nil {
			return Query{}, err
		}
		query.Limit = &limit
	}

	if p.consumeKeyword("OFFSET") {
		offset, err := p.parseNonNegativeInt("OFFSET")
		if err != nil {
			return Query{}, err
		}
		query.Offset = &offset
	}

	return query, nil
}

func (p *queryParser) parseTarget() (Target, error) {
	tok := p.current()
	if tok.kind != tokenIdent {
		return "", p.errorf("expected query target")
	}
	p.advance()

	target := Target(strings.ToLower(tok.literal))
	if target != TargetObjects && target != TargetRelations {
		return "", p.errorf("unsupported query target %q", tok.literal)
	}

	return target, nil
}

func (p *queryParser) parseBoolExpr() (Expr, error) {
	left, err := p.parseAndExpr()
	if err != nil {
		return nil, err
	}

	terms := []Expr{left}
	for p.consumeKeyword("OR") {
		right, err := p.parseAndExpr()
		if err != nil {
			return nil, err
		}
		terms = append(terms, right)
	}
	if len(terms) == 1 {
		return pointerExpr(left), nil
	}

	return &BoolExpr{Op: BoolOr, Terms: terms}, nil
}

func (p *queryParser) parseAndExpr() (Expr, error) {
	first, err := p.parseUnaryExpr()
	if err != nil {
		return nil, err
	}

	terms := []Expr{first}
	for p.consumeKeyword("AND") {
		next, err := p.parseUnaryExpr()
		if err != nil {
			return nil, err
		}
		terms = append(terms, next)
	}
	if len(terms) == 1 {
		return first, nil
	}

	return &BoolExpr{Op: BoolAnd, Terms: terms}, nil
}

func (p *queryParser) parseUnaryExpr() (Expr, error) {
	p.depth++
	defer func() { p.depth-- }()
	if p.depth > maxExpressionDepth {
		return nil, p.errorf("expression nesting exceeds %d", maxExpressionDepth)
	}
	if p.consumeKeyword("NOT") {
		expr, err := p.parseUnaryExpr()
		if err != nil {
			return nil, err
		}
		return NotExpr{Expr: expr}, nil
	}

	if p.isKeyword("HAS_RELATION") && p.peek().kind == tokenLParen {
		return p.parseRelationPredicate()
	}

	if p.isKeyword("BUCKET") && p.peek().kind == tokenLParen {
		return p.parseBucketPredicate()
	}

	if p.consume(tokenLParen) {
		expr, err := p.parseBoolExpr()
		if err != nil {
			return nil, err
		}
		if !p.consume(tokenRParen) {
			return nil, p.errorf("expected ) after boolean expression")
		}
		return expr, nil
	}

	return p.parseComparison()
}

func (p *queryParser) parseRelationPredicate() (Expr, error) {
	p.advance()
	if !p.consume(tokenLParen) {
		return nil, p.errorf("expected ( after has_relation")
	}

	relationType := p.current()
	if relationType.kind != tokenString {
		return nil, p.errorf("expected relation type string")
	}
	p.advance()
	if err := validateRelationType(relationType.literal); err != nil {
		return nil, p.errorf("%s", err)
	}

	direction := RelationAny
	if p.consume(tokenComma) {
		directionToken := p.current()
		if directionToken.kind != tokenString {
			return nil, p.errorf("expected relation direction string")
		}
		p.advance()

		parsedDirection, err := parseRelationDirection(directionToken.literal)
		if err != nil {
			return nil, p.errorf("%s", err)
		}
		direction = parsedDirection
	}

	if !p.consume(tokenRParen) {
		return nil, p.errorf("expected ) after has_relation")
	}

	return RelationPredicate{Type: relationType.literal, Direction: direction}, nil
}

func (p *queryParser) parseBucketPredicate() (Expr, error) {
	p.advance()
	if !p.consume(tokenLParen) {
		return nil, p.errorf("expected ( after bucket")
	}

	bucketName := p.current()
	if bucketName.kind != tokenString {
		return nil, p.errorf("expected bucket name string")
	}
	p.advance()
	if err := validateBucketName(bucketName.literal); err != nil {
		return nil, p.errorf("%s", err)
	}

	if !p.consume(tokenRParen) {
		return nil, p.errorf("expected ) after bucket")
	}

	return BucketPredicate{Name: bucketName.literal}, nil
}

func (p *queryParser) parseComparison() (Expr, error) {
	left, err := p.parseOperand()
	if err != nil {
		return nil, err
	}

	if p.consumeKeyword("IN") {
		return p.parseInComparison(left)
	}
	if p.consumeKeyword("BETWEEN") {
		return p.parseBetweenComparison(left)
	}
	if p.consumeKeyword("IS") {
		return p.parseNullComparison(left)
	}

	op, err := p.parseComparisonOp()
	if err != nil {
		return nil, err
	}

	right, err := p.parseOperand()
	if err != nil {
		return nil, err
	}

	return Comparison{Op: op, Left: left, Right: right}, nil
}

func (p *queryParser) parseComparisonOp() (ComparisonOp, error) {
	tok := p.current()
	switch tok.literal {
	case "=":
		p.advance()
		return OpEq, nil
	case "!=", "<>":
		p.advance()
		return OpNeq, nil
	case "<":
		p.advance()
		return OpLt, nil
	case "<=":
		p.advance()
		return OpLte, nil
	case ">":
		p.advance()
		return OpGt, nil
	case ">=":
		p.advance()
		return OpGte, nil
	default:
		if p.consumeKeyword("LIKE") {
			return OpLike, nil
		}
		if p.consumeKeyword("ILIKE") {
			return OpILike, nil
		}
		return "", p.errorf("expected comparison operator")
	}
}

func (p *queryParser) parseInComparison(left Expr) (Expr, error) {
	if !p.consume(tokenLParen) {
		return nil, p.errorf("expected ( after IN")
	}
	if p.at(tokenRParen) {
		return nil, p.errorf("IN list must not be empty")
	}

	values := []Expr{}
	for {
		value, err := p.parseOperand()
		if err != nil {
			return nil, err
		}
		values = append(values, value)

		if !p.consume(tokenComma) {
			break
		}
		if p.at(tokenRParen) {
			return nil, p.errorf("expected expression after comma")
		}
	}

	if !p.consume(tokenRParen) {
		return nil, p.errorf("expected ) after IN list")
	}

	return InComparison{Left: left, Values: values}, nil
}

func (p *queryParser) parseBetweenComparison(left Expr) (Expr, error) {
	lower, err := p.parseOperand()
	if err != nil {
		return nil, err
	}
	if !p.consumeKeyword("AND") {
		return nil, p.errorf("expected AND in BETWEEN comparison")
	}
	upper, err := p.parseOperand()
	if err != nil {
		return nil, err
	}

	return BetweenComparison{Left: left, Lower: lower, Upper: upper}, nil
}

func (p *queryParser) parseNullComparison(left Expr) (Expr, error) {
	not := p.consumeKeyword("NOT")
	if !p.consumeKeyword("NULL") {
		return nil, p.errorf("expected NULL after IS")
	}

	return NullComparison{Left: left, Not: not}, nil
}

func (p *queryParser) parseOperand() (Expr, error) {
	return p.parseAdditiveExpr()
}

func (p *queryParser) parseAdditiveExpr() (Expr, error) {
	left, err := p.parseCastOperand()
	if err != nil {
		return nil, err
	}

	for p.at(tokenOperator) {
		operator := p.current().literal
		if operator != "+" && operator != "-" {
			break
		}
		p.advance()

		right, err := p.parseCastOperand()
		if err != nil {
			return nil, err
		}

		arithOp := ArithAdd
		if operator == "-" {
			arithOp = ArithSub
		}
		left = ArithmeticExpr{Op: arithOp, Left: left, Right: right}
	}

	return left, nil
}

func (p *queryParser) parseCastOperand() (Expr, error) {
	expr, err := p.parsePrimary()
	if err != nil {
		return nil, err
	}

	return p.parsePostfixCasts(expr)
}

func (p *queryParser) parsePrimary() (Expr, error) {
	p.depth++
	defer func() { p.depth-- }()
	if p.depth > maxExpressionDepth {
		return nil, p.errorf("expression nesting exceeds %d", maxExpressionDepth)
	}
	if p.isKeyword("CAST") {
		return p.parseCastCall()
	}
	if p.isKeyword("NOW") && p.peek().kind == tokenLParen {
		return p.parseNowCall()
	}

	tok := p.current()
	switch tok.kind {
	case tokenIdent:
		if p.isKeyword("ATTR") && p.peek().kind == tokenLParen {
			attr, err := p.parseAttrRef()
			if err != nil {
				return nil, err
			}
			return attr, nil
		}
		if p.isKeyword("TRUE") {
			p.advance()
			return BoolLiteral{Value: true}, nil
		}
		if p.isKeyword("FALSE") {
			p.advance()
			return BoolLiteral{Value: false}, nil
		}
		if p.isKeyword("NULL") {
			p.advance()
			return NullLiteral{}, nil
		}
		if p.isKeyword("TIMESTAMP") {
			return p.parseTimestampLiteral()
		}
		if p.isKeyword("DATE") {
			return p.parseDateLiteral()
		}
		if p.isKeyword("INTERVAL") {
			return p.parseIntervalLiteral()
		}
		p.advance()
		return FieldRef{Name: tok.literal}, nil
	case tokenString:
		p.advance()
		return StringLiteral{Value: tok.literal}, nil
	case tokenNumber:
		p.advance()
		if strings.Contains(tok.literal, ".") {
			value, err := strconv.ParseFloat(tok.literal, 64)
			if err != nil {
				return nil, p.errorf("invalid float literal %q", tok.literal)
			}
			return FloatLiteral{Value: value}, nil
		}
		value, err := strconv.ParseInt(tok.literal, 10, 64)
		if err != nil {
			return nil, p.errorf("invalid integer literal %q", tok.literal)
		}
		return IntLiteral{Value: value}, nil
	default:
		return nil, p.errorf("expected expression")
	}
}

func (p *queryParser) parsePostfixCasts(expr Expr) (Expr, error) {
	for p.consume(tokenCast) {
		castType, err := p.parseCastTypeName()
		if err != nil {
			return nil, err
		}
		expr = CastExpr{Expr: expr, Type: castType}
	}

	return expr, nil
}

func (p *queryParser) parseCastCall() (Expr, error) {
	p.advance()
	if !p.consume(tokenLParen) {
		return nil, p.errorf("expected ( after CAST")
	}

	inner, err := p.parseOperand()
	if err != nil {
		return nil, err
	}
	if !p.consumeKeyword("AS") {
		return nil, p.errorf("expected AS in CAST expression")
	}

	castType, err := p.parseCastTypeName()
	if err != nil {
		return nil, err
	}
	if !p.consume(tokenRParen) {
		return nil, p.errorf("expected ) after CAST expression")
	}

	return CastExpr{Expr: inner, Type: castType}, nil
}

func (p *queryParser) parseCastTypeName() (ValueType, error) {
	tok := p.current()
	if tok.kind != tokenIdent {
		return "", p.errorf("expected cast type name")
	}
	p.advance()

	return ParseCastType(tok.literal)
}

func (p *queryParser) parseNowCall() (Expr, error) {
	p.advance()
	if !p.consume(tokenLParen) {
		return nil, p.errorf("expected ( after now")
	}
	if !p.at(tokenRParen) {
		return nil, p.errorf("now() does not accept arguments")
	}
	p.advance()

	return NowExpr{}, nil
}

func (p *queryParser) parseIntervalLiteral() (Expr, error) {
	p.advance()

	tok := p.current()
	if tok.kind != tokenString {
		return nil, p.errorf("expected interval string")
	}
	p.advance()

	value, err := ParseIntervalValue(tok.literal)
	if err != nil {
		return nil, p.errorf("%s", err)
	}

	return IntervalLiteral{Value: value}, nil
}

func (p *queryParser) parseDateLiteral() (Expr, error) {
	p.advance()

	tok := p.current()
	if tok.kind != tokenString {
		return nil, p.errorf("expected date string")
	}
	p.advance()

	value, err := time.Parse("2006-01-02", tok.literal)
	if err != nil {
		return nil, p.errorf("invalid date literal %q", tok.literal)
	}

	return TimestampLiteral{Value: value.UTC()}, nil
}

func (p *queryParser) parseTimestampLiteral() (Expr, error) {
	p.advance()

	tok := p.current()
	if tok.kind != tokenString {
		return nil, p.errorf("expected timestamp string")
	}
	p.advance()

	value, err := time.Parse(time.RFC3339, tok.literal)
	if err != nil {
		return nil, p.errorf("invalid timestamp literal %q", tok.literal)
	}

	return TimestampLiteral{Value: value}, nil
}

func (p *queryParser) parseAttrRef() (Expr, error) {
	p.advance()
	if !p.consume(tokenLParen) {
		return nil, p.errorf("expected ( after attr")
	}

	path := p.current()
	if path.kind != tokenString {
		return nil, p.errorf("expected attribute path string")
	}
	p.advance()

	if err := validateAttributePath(path.literal); err != nil {
		return nil, p.errorf("%s", err)
	}
	if !p.consume(tokenRParen) {
		return nil, p.errorf("expected ) after attribute path")
	}

	return AttrRef{Path: path.literal}, nil
}

func (p *queryParser) parseOrderBy() ([]OrderExpr, error) {
	orderBy := []OrderExpr{}
	for {
		expr, err := p.parseOperand()
		if err != nil {
			return nil, err
		}

		direction := SortAsc
		if p.consumeKeyword("ASC") {
			direction = SortAsc
		} else if p.consumeKeyword("DESC") {
			direction = SortDesc
		}

		orderBy = append(orderBy, OrderExpr{
			Expr:      expr,
			Direction: direction,
		})

		if !p.consume(tokenComma) {
			break
		}
		if p.at(tokenEOF) {
			return nil, p.errorf("expected ORDER BY expression after comma")
		}
	}

	return orderBy, nil
}

func (p *queryParser) parseNonNegativeInt(label string) (int, error) {
	tok := p.current()
	if tok.kind != tokenNumber {
		return 0, p.errorf("expected integer %s", label)
	}
	p.advance()

	value, err := strconv.Atoi(tok.literal)
	if err != nil || value < 0 {
		return 0, p.errorf("invalid %s %q", label, tok.literal)
	}

	return value, nil
}

func (p *queryParser) current() token {
	if p.pos >= len(p.tokens) {
		return token{kind: tokenEOF}
	}
	return p.tokens[p.pos]
}

func (p *queryParser) peek() token {
	if p.pos+1 >= len(p.tokens) {
		return token{kind: tokenEOF}
	}
	return p.tokens[p.pos+1]
}

func (p *queryParser) advance() {
	if !p.at(tokenEOF) {
		p.pos++
	}
}

func (p *queryParser) at(kind tokenKind) bool {
	return p.current().kind == kind
}

func (p *queryParser) consume(kind tokenKind) bool {
	if !p.at(kind) {
		return false
	}
	p.advance()
	return true
}

func (p *queryParser) consumeKeyword(keyword string) bool {
	if !p.isKeyword(keyword) {
		return false
	}
	p.advance()
	return true
}

func (p *queryParser) isKeyword(keyword string) bool {
	tok := p.current()
	return tok.kind == tokenIdent && strings.EqualFold(tok.literal, keyword)
}

func (p *queryParser) errorf(format string, args ...any) error {
	return fmt.Errorf("parse PithosysQL at token %d: %s", p.pos, fmt.Sprintf(format, args...))
}

func pointerExpr(expr Expr) Expr {
	switch typed := expr.(type) {
	case Comparison:
		return &typed
	case InComparison:
		return &typed
	case BetweenComparison:
		return &typed
	case NullComparison:
		return &typed
	case NotExpr:
		return &typed
	case RelationPredicate:
		return &typed
	case BucketPredicate:
		return &typed
	default:
		return expr
	}
}

func validateAttributePath(path string) error {
	if strings.TrimSpace(path) == "" {
		return fmt.Errorf("attribute path is empty")
	}
	if strings.TrimSpace(path) != path {
		return fmt.Errorf("attribute path has surrounding whitespace")
	}

	for index, segment := range strings.Split(path, ".") {
		if segment == "" {
			return fmt.Errorf("attribute path segment %d is empty", index)
		}
		if strings.TrimSpace(segment) != segment {
			return fmt.Errorf("attribute path segment %d has surrounding whitespace", index)
		}
	}

	return nil
}

func validateRelationType(relationType string) error {
	if strings.TrimSpace(relationType) == "" {
		return fmt.Errorf("relation type is empty")
	}
	if strings.TrimSpace(relationType) != relationType {
		return fmt.Errorf("relation type has surrounding whitespace")
	}

	return nil
}

func validateBucketName(bucketName string) error {
	if strings.TrimSpace(bucketName) == "" {
		return fmt.Errorf("bucket name is empty")
	}
	if strings.TrimSpace(bucketName) != bucketName {
		return fmt.Errorf("bucket name has surrounding whitespace")
	}

	return nil
}

func parseRelationDirection(value string) (RelationDirection, error) {
	switch RelationDirection(value) {
	case RelationAny:
		return RelationAny, nil
	case RelationOut:
		return RelationOut, nil
	case RelationIn:
		return RelationIn, nil
	default:
		return "", fmt.Errorf("unsupported relation direction %q", value)
	}
}

type tokenKind int

const (
	tokenEOF tokenKind = iota
	tokenIdent
	tokenString
	tokenNumber
	tokenOperator
	tokenLParen
	tokenRParen
	tokenComma
	tokenSemicolon
	tokenCast
)

type token struct {
	kind    tokenKind
	literal string
}

func lex(input string) ([]token, error) {
	tokens := []token{}
	for i := 0; i < len(input); {
		r := rune(input[i])
		if unicode.IsSpace(r) {
			i++
			continue
		}

		if isIdentStart(r) {
			start := i
			i++
			for i < len(input) && isIdentPart(rune(input[i])) {
				i++
			}
			tokens = append(tokens, token{kind: tokenIdent, literal: input[start:i]})
			continue
		}

		if unicode.IsDigit(r) {
			literal, next, err := scanNumber(input, i)
			if err != nil {
				return nil, err
			}
			tokens = append(tokens, token{kind: tokenNumber, literal: literal})
			i = next
			continue
		}

		switch input[i] {
		case '\'':
			value, next, err := scanString(input, i)
			if err != nil {
				return nil, err
			}
			tokens = append(tokens, token{kind: tokenString, literal: value})
			i = next
		case '(':
			tokens = append(tokens, token{kind: tokenLParen, literal: "("})
			i++
		case ')':
			tokens = append(tokens, token{kind: tokenRParen, literal: ")"})
			i++
		case ',':
			tokens = append(tokens, token{kind: tokenComma, literal: ","})
			i++
		case ';':
			tokens = append(tokens, token{kind: tokenSemicolon, literal: ";"})
			i++
		case ':':
			if i+1 >= len(input) || input[i+1] != ':' {
				return nil, fmt.Errorf("lex PithosysQL at byte %d: unexpected character ':'", i)
			}
			tokens = append(tokens, token{kind: tokenCast, literal: "::"})
			i += 2
		case '+', '-':
			tokens = append(tokens, token{kind: tokenOperator, literal: string(input[i])})
			i++
		case '=', '<', '>', '!':
			operator, next, err := scanOperator(input, i)
			if err != nil {
				return nil, err
			}
			tokens = append(tokens, token{kind: tokenOperator, literal: operator})
			i = next
		default:
			return nil, fmt.Errorf("lex PithosysQL at byte %d: unexpected character %q", i, input[i])
		}
	}

	tokens = append(tokens, token{kind: tokenEOF})
	return tokens, nil
}

func scanString(input string, start int) (string, int, error) {
	var builder strings.Builder
	for i := start + 1; i < len(input); i++ {
		if input[i] != '\'' {
			builder.WriteByte(input[i])
			continue
		}

		if i+1 < len(input) && input[i+1] == '\'' {
			builder.WriteByte('\'')
			i++
			continue
		}

		return builder.String(), i + 1, nil
	}

	return "", 0, fmt.Errorf("lex PithosysQL at byte %d: unterminated string", start)
}

func scanNumber(input string, start int) (string, int, error) {
	i := start
	for i < len(input) && unicode.IsDigit(rune(input[i])) {
		i++
	}

	if i >= len(input) || input[i] != '.' {
		return input[start:i], i, nil
	}

	i++
	fractionStart := i
	for i < len(input) && unicode.IsDigit(rune(input[i])) {
		i++
	}
	if fractionStart == i {
		return "", 0, fmt.Errorf("lex PithosysQL at byte %d: invalid float literal", start)
	}

	return input[start:i], i, nil
}

func scanOperator(input string, start int) (string, int, error) {
	if start+1 < len(input) {
		two := input[start : start+2]
		switch two {
		case "!=", "<=", ">=", "<>":
			return two, start + 2, nil
		}
	}

	switch input[start] {
	case '=', '<', '>':
		return input[start : start+1], start + 1, nil
	default:
		return "", 0, fmt.Errorf("lex PithosysQL at byte %d: unsupported operator", start)
	}
}

func isIdentStart(r rune) bool {
	return unicode.IsLetter(r) || r == '_'
}

func isIdentPart(r rune) bool {
	return unicode.IsLetter(r) || unicode.IsDigit(r) || r == '_'
}
