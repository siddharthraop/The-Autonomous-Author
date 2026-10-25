# Troubleshooting NAT

## Connections are reused too early

A closed TCP connection stays in TIME_WAIT for 120 seconds before its port can
be reused. If new connections fail because no ports are free, lower the value
with `--tcp-time-wait-timeout`.

## Idle connections drop

Check the established timeout with `natctl describe`. The default is
{{ nat_tcp_established_default }}.
