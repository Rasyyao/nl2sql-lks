"""
test_upgrade.py — Verification script for the NL2SQL pipeline upgrade.
Tests both intent_classifier.py and schema_retrieval.py independently.
"""

print("=" * 60)
print("TEST 1: IntentClassifier")
print("=" * 60)

from intent_classifier import intent_classifier

test_queries = [
    # SELECT intent
    ("berikan daftar dosen", "SELECT"),
    ("tampilkan semua dosen", "SELECT"),
    ("siapa saja dosen di fakultas teknik", "SELECT"),
    ("total gaji pokok dosen", "SELECT"),
    ("berapa banyak fakultas", "SELECT"),
    ("show me all data", "SELECT"),
    # GREETING
    ("halo", "GREETING"),
    ("selamat pagi", "GREETING"),
    ("hai", "GREETING"),
    # OUT_OF_SCOPE
    ("siapa presiden indonesia", "OUT_OF_SCOPE"),
    ("buatkan kue", "OUT_OF_SCOPE"),
    ("what is the weather", "OUT_OF_SCOPE"),
    # CLARIFICATION
    ("maksudnya apa", "CLARIFICATION"),
    ("bisa dijelaskan", "CLARIFICATION"),
    # SCHEMA_QUESTION
    ("tabel apa saja yang ada", "SCHEMA_QUESTION"),
    ("struktur database", "SCHEMA_QUESTION"),
    # EDUKASI_QUESTION
    ("apa itu nl2sql", "EDUKASI_QUESTION"),
    ("cara kerja agent ini", "EDUKASI_QUESTION"),
]

passed = 0
failed = 0
for query, expected in test_queries:
    result = intent_classifier.classify(query)
    status = "✅" if result["intent"] == expected else "❌"
    if result["intent"] == expected:
        passed += 1
    else:
        failed += 1
    print(f"  {status} \"{query}\"")
    print(f"      → {result['intent']} (confidence: {result['confidence']:.4f}), expected: {expected}")

print(f"\nIntent Classifier: {passed}/{passed+failed} passed\n")

print("=" * 60)
print("TEST 2: SchemaRetriever")
print("=" * 60)

from schema_retrieval import schema_retriever

retrieval_tests = [
    ("daftar dosen fakultas teknik", ["dosen", "fakultas"]),
    ("total gaji pokok dosen", ["remunerasi", "dosen"]),
    ("jabatan fungsional lektor", ["jabatan_fungsional"]),
    ("nama fakultas dan dekan", ["fakultas"]),
    ("tunjangan kinerja remunerasi", ["remunerasi"]),
]

for query, expected_tables in retrieval_tests:
    tables = schema_retriever.get_relevant_table_names(query, top_k=2)
    all_found = all(t in tables for t in expected_tables)
    status = "✅" if all_found else "⚠️"
    print(f"  {status} \"{query}\"")
    print(f"      → Top-2: {tables}, expected to contain: {expected_tables}")
    sims = schema_retriever.get_similarities(query)
    print(f"      → Similarities: {sims}")

print()

# Token reduction measurement
full_schema = schema_retriever.get_relevant_schema("test", top_k=4)
reduced_schema = schema_retriever.get_relevant_schema("gaji dosen", top_k=2)
full_tokens = len(full_schema.split())
reduced_tokens = len(reduced_schema.split())
savings = round((1 - reduced_tokens / full_tokens) * 100)
print(f"Token reduction: Full={full_tokens} words, Reduced={reduced_tokens} words, Savings={savings}%")

print()
print("=" * 60)
print("TEST 3: Sample schema output (top_k=2)")
print("=" * 60)
sample = schema_retriever.get_relevant_schema("total gaji dosen per fakultas", top_k=2)
print(sample)
