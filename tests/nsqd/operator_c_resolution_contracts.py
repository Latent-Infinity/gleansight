from __future__ import annotations

from typing import Final

PROTOCOL_PATH: Final = "../nsqd-operator-evidence-resolution-2026-09-09/protocol.json"

EXTRACT_BINDINGS: Final = {
    "A-SOFT-CODEBOOK": ("arXiv:2602.04643", "v2", 1),
    "A-MULTI-RESOLUTION": ("arXiv:2602.04643", "v2", 1),
    "BRIDGE-THREE-REGIME": ("arXiv:2604.20949", "v1", 2),
    "BRIDGE-IDENTIFIABILITY": ("arXiv:2604.20949", "v1", 2),
    "BRIDGE-REAL-MARKET-LIMIT": ("arXiv:2604.20949", "v1", 26),
    "BRIDGE-SAMPLE-LIMIT": ("arXiv:2604.20949", "v1", 27),
    "C-INTRINSIC-NETWORK": ("arXiv:1402.2198", "v1", 1),
    "C-LIQUIDITY-STRESS": ("arXiv:1402.2198", "v1", 1),
    "C-LIQUIDITY-DEFINITION": ("arXiv:1402.2198", "v1", 10),
}

EXTRACT_QUOTE_SHA256: Final = {
    "A-SOFT-CODEBOOK": "04fdafedf06a48ee6e315bf75c9d8f9673b96b43facb8afb29ca1a0f95971ead",
    "A-MULTI-RESOLUTION": "18cf5948d3fc49c063f73aba8c1d094e99f620a868935a769206b1067592a475",
    "BRIDGE-THREE-REGIME": "20e54e52f70d890a0f9f6f9727a69467069777d7ffbb0dd4622aa9694a46f547",
    "BRIDGE-IDENTIFIABILITY": "34e671f8404cf053ebf089a36d46dafa7645871ee3580046ab381231d3179f8f",
    "BRIDGE-REAL-MARKET-LIMIT": "7e753d00531fb200ff9b849b45198b1820b8c883f59e21630500046e00f4e105",
    "BRIDGE-SAMPLE-LIMIT": "207d6103cefb7b52911e698fda95f20b9e4d0e409e6129deaf2b999d731f7388",
    "C-INTRINSIC-NETWORK": "2b3f47e43b3bd821f5276cbb02028c41418ac56bc54fd8c1a4389d367e8a95ae",
    "C-LIQUIDITY-STRESS": "18b65d21a59ee6f310fb47d8b602bcc7fd24bda42f8cee2619d1b51fde8a05bb",
    "C-LIQUIDITY-DEFINITION": "819d9bcf5e352447b26e238443489e62d4c8ed0acd4919fee5987d1250f42a04",
}

INTERACTION_STATUS: Final = {
    "direct_a_to_c_prior_art": "not_observed_within_bounded_queries",
    "direct_citation": "not_observed_within_bounded_queries",
    "co_citation": "not_observed_within_bounded_queries",
    "author_overlap": "not_observed_within_bounded_queries",
    "direct_mention": "not_observed_within_bounded_queries",
    "counterevidence": "observed_in_exact_passages",
    "semantic_scholar_availability": "unavailable_from_service",
}
CONTROLS: Final = {
    "normalized_shared_term_control_under_identical_query_budget": (
        "not_observed_within_bounded_queries"
    ),
    "sha256_seeded_shuffled_literature_pair_control_under_identical_query_budget": (
        "unavailable_nonreproducible"
    ),
}
HISTORY: Final = {
    "new_primary_source": "arXiv:2604.20949v1",
    "distinct_middle_object": "latent_limit_order_book_build_up_regime",
    "finance_native_surface_overlap": True,
    "renamed_positive_claim": False,
    "conclusion": "legitimate_new_negative_cycle",
}
PREDECESSOR: Final = {
    "packet_path": "../nsqd-operator-c-evidence-2026-09-09-resolution",
    "packet_digest": "406fccd5d072db490e3abcd067b0327b3817effcbe85cac49f0eaa40be8cb4d3",
    "status": "rejected_source_replay_and_control_derivation",
    "supersedes": True,
}

EXPECTED_QUERY_URLS: Final = {
    "arxiv-source-identity": (
        "https://export.arxiv.org/api/query?id_list=2602.04643v2,2604.20949v1,1402.2198v1&max_results=3",
        "https://export.arxiv.org/api/query?id_list=2602.04643v2%2c2604.20949v1%2c1402.2198v1&max_results=3",
    ),
    "openalex-exact-a-bridge": "https://api.openalex.org/works?search=%22SC-JEPA%22+%22Early+Detection+of+Latent+Microstructure+Regimes+in+Limit+Order+Books%22&per-page=25",
    "openalex-exact-bridge-c": "https://api.openalex.org/works?search=%22Early+Detection+of+Latent+Microstructure+Regimes+in+Limit+Order+Books%22+%22Multi-scale+Representation+of+High+Frequency+Market+Liquidity%22&per-page=25",
    "openalex-exact-a-c": "https://api.openalex.org/works?search=%22SC-JEPA%22+%22Multi-scale+Representation+of+High+Frequency+Market+Liquidity%22&per-page=25",
    "openalex-normalized-a-bridge": "https://api.openalex.org/works?search=%22soft+codebook%22+%22latent+build-up+regime%22&per-page=25",
    "openalex-normalized-bridge-c": "https://api.openalex.org/works?search=%22latent+build-up+regime%22+%22Intrinsic+Network+liquidity%22&per-page=25",
    "openalex-normalized-a-c": "https://api.openalex.org/works?search=%22time-series+anomaly+prediction%22+%22market+liquidity+stress%22&per-page=25",
    "openalex-shuffled-1": "https://api.openalex.org/works?search=%22SC-JEPA%22+%22Algorithmic+Monitoring%3A+Measuring+Market+Stress+with+Machine+Learning%22&per-page=25",
    "openalex-shuffled-2": "https://api.openalex.org/works?search=%22Early+Detection+of+Latent+Microstructure+Regimes+in+Limit+Order+Books%22+%22An+Interpretable+Ensemble-Based+Generative+Framework+for+Anomaly+Detection+in+High-Dimensional+Financial+Time+Series%22&per-page=25",
    "openalex-shuffled-3": "https://api.openalex.org/works?search=%22Multi-scale+Representation+of+High+Frequency+Market+Liquidity%22+%22The+Market%E2%80%99s+Conditioning+Representation%3A+Equilibrium%2C+Crowding%2C+and+Convention+Multiplicity%22&per-page=25",
    "s2-a-citations-references": "https://api.semanticscholar.org/graph/v1/paper/ARXIV:2602.04643?fields=paperId,title,authors,citations.paperId,references.paperId",
    "s2-bridge-citations-references": "https://api.semanticscholar.org/graph/v1/paper/ARXIV:2604.20949?fields=paperId,title,authors,citations.paperId,references.paperId",
    "s2-c-citations-references": "https://api.semanticscholar.org/graph/v1/paper/ARXIV:1402.2198?fields=paperId,title,authors,citations.paperId,references.paperId",
}

BATCH_CONTRACTS: Final = (
    (
        "source identity plus exact-title interaction and provider citation-reference checks",
        None,
        (
            "arxiv-source-identity",
            "openalex-exact-a-bridge",
            "openalex-exact-bridge-c",
            "openalex-exact-a-c",
            "s2-a-citations-references",
            "s2-bridge-citations-references",
            "s2-c-citations-references",
        ),
    ),
    (
        "normalized shared-term control under the identical result budget",
        "normalized_shared_term_control_under_identical_query_budget",
        ("openalex-normalized-a-bridge", "openalex-normalized-bridge-c", "openalex-normalized-a-c"),
    ),
    (
        "SHA256-seeded shuffled literature pair control under the identical result budget",
        "sha256_seeded_shuffled_literature_pair_control_under_identical_query_budget",
        ("openalex-shuffled-1", "openalex-shuffled-2", "openalex-shuffled-3"),
    ),
)

EXTRACT_LOCATIONS: Final = {
    "A-SOFT-CODEBOOK": (1, "Abstract", "Abstract, PDF p. 1", False),
    "A-MULTI-RESOLUTION": (1, "Abstract", "Abstract, PDF p. 1", False),
    "BRIDGE-THREE-REGIME": (2, "Abstract", "Abstract, PDF p. 2", False),
    "BRIDGE-IDENTIFIABILITY": (2, "Abstract", "Abstract, PDF p. 2", False),
    "BRIDGE-REAL-MARKET-LIMIT": (
        26,
        "9 Preliminary Illustrative Real-Data Application",
        "Section 9, physical PDF p. 26; printed-page locator unavailable",
        True,
    ),
    "BRIDGE-SAMPLE-LIMIT": (
        27,
        "9 Preliminary Illustrative Real-Data Application",
        "Section 9, PDF p. 27",
        False,
    ),
    "C-INTRINSIC-NETWORK": (1, "Abstract", "Abstract, PDF p. 1", False),
    "C-LIQUIDITY-STRESS": (1, "Abstract", "Abstract, PDF p. 1", False),
    "C-LIQUIDITY-DEFINITION": (
        10,
        "6 Price trajectory unlikeliness",
        "Section 6, PDF p. 10",
        False,
    ),
}

INTERACTION_CONTRACTS: Final = {
    "direct_a_to_c_prior_art": (0, ("openalex-exact-a-c", "openalex-normalized-a-c"), ()),
    "direct_citation": (
        0,
        ("openalex-exact-a-bridge", "openalex-exact-bridge-c", "openalex-exact-a-c"),
        (),
    ),
    "co_citation": (
        0,
        ("openalex-exact-a-bridge", "openalex-exact-bridge-c", "openalex-exact-a-c"),
        (),
    ),
    "author_overlap": (0, ("arxiv-source-identity",), ()),
    "direct_mention": (
        0,
        (
            "openalex-exact-a-bridge",
            "openalex-exact-bridge-c",
            "openalex-exact-a-c",
            "openalex-normalized-a-bridge",
            "openalex-normalized-bridge-c",
            "openalex-normalized-a-c",
        ),
        (),
    ),
    "counterevidence": (
        2,
        ("arxiv-source-identity",),
        ("BRIDGE-REAL-MARKET-LIMIT", "BRIDGE-SAMPLE-LIMIT"),
    ),
    "semantic_scholar_availability": (
        None,
        (
            "s2-a-citations-references",
            "s2-bridge-citations-references",
            "s2-c-citations-references",
        ),
        (),
    ),
}
