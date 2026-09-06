FROM golang:1.27.1-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -o /out/api ./apps/api && \
    CGO_ENABLED=0 go build -trimpath -o /out/worker ./apps/worker && \
    CGO_ENABLED=0 go build -trimpath -o /out/demo ./cmd/demo
FROM alpine:3.24 AS runtime
RUN apk add --no-cache ca-certificates && adduser -D -u 10001 pithosys
WORKDIR /app
COPY --from=build /out/ /app/
COPY packages/storage/migrations /app/packages/storage/migrations
USER pithosys
CMD ["/app/api"]
