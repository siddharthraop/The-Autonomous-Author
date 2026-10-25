"""NAT gateway timeouts. Each entry is reader-visible: docs state its default, flag and field."""

TIMEOUTS = {
    "tcp_established": {
        "label": "TCP established",
        "default": 1200,
        "unit": "seconds",
        "flag": "--tcp-established-idle-timeout",
        "field": "tcpEstablishedIdleTimeoutSec",
    },
    "tcp_transitory": {
        "label": "TCP transitory",
        "default": 30,
        "unit": "seconds",
        "flag": "--tcp-transitory-idle-timeout",
        "field": "tcpTransitoryIdleTimeoutSec",
    },
    "tcp_time_wait": {
        "label": "TCP TIME_WAIT",
        "default": 30,
        "unit": "seconds",
        "flag": "--tcp-time-wait-timeout",
        "field": "tcpTimeWaitTimeoutSec",
        "minimum": 15,
    },
    "udp": {
        "label": "UDP",
        "default": 30,
        "unit": "seconds",
        "flag": "--udp-idle-timeout",
        "field": "udpIdleTimeoutSec",
    },
}

# Fields printed by `natctl describe`.
DESCRIBE_FIELDS = [
    "name",
    "tcpEstablishedIdleTimeoutSec",
    "tcpTransitoryIdleTimeoutSec",
    "tcpTimeWaitTimeoutSec",
    "udpIdleTimeoutSec",
    "effectiveTcpTimeWaitTimeoutSec",
]
