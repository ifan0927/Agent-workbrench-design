"""Reject test/review evidence belonging to another candidate or requirement."""


def eligible(candidate, verification, review, requirement_sha256):
    return (verification.get('status') == 'pass'
            and verification.get('candidate', {}).get('commit') == candidate['commit']
            and verification.get('candidate', {}).get('tree') == candidate['tree']
            and review.get('commit') == candidate['commit']
            and review.get('requirement_sha256') == requirement_sha256
            and review.get('approved') is True)
