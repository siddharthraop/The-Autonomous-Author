# Tune NAT configuration

A NAT gateway closes idle connections when a timeout expires. This page lists
the timeouts, their defaults, and the flags that change them.

## Timeouts

| Timeout | Default | Flag |
| --- | --- | --- |
| TCP established | {{ nat_tcp_established_default }} | `--tcp-established-idle-timeout` |
| TCP transitory | {{ nat_tcp_transitory_default }} | `--tcp-transitory-idle-timeout` |
| TCP TIME_WAIT | {{ nat_tcp_time_wait_default }} | `--tcp-time-wait-timeout` |
| UDP | {{ nat_udp_default }} | `--udp-idle-timeout` |

[NEEDS INPUT: C1 — UDP: minimum changed from None to 10. How should this page describe it?]

## Change a timeout

To change a timeout, run `natctl update` with the flag for that timeout:

```bash
natctl update my-gateway --tcp-time-wait-timeout=60
```

## Describe a gateway

To see the settings of a gateway, run `natctl describe`:

```bash
natctl describe my-gateway
```

See also [Troubleshooting](troubleshooting.md).
