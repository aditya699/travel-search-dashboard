// Power Query (M) for Power BI Desktop: loads the exported star schema from Parquet.
//
// 1. Home → Transform data → Manage parameters → New parameter:
//      Name: DataFolder   Type: Text
//      Current value: the full path of server\data\powerbi, ending in a backslash,
//      e.g. D:\code\travel-search-dashboard\server\data\powerbi\
// 2. Home → New source → Blank query → Advanced editor. Paste ONE block below per
//    query and name the query exactly as the comment says (the DAX expects these names).
//
// Parquet keeps column types (dates stay dates, numbers stay numbers), so there is no
// "Changed Type" step to maintain. The CSV files are there if you prefer them.


// ---- query name: fact_fare_quote ------------------------------------------------
let
    Source = Parquet.Document(File.Contents(DataFolder & "fact_fare_quote.parquet"))
in
    Source


// ---- query name: quarantine -------------------------------------------------------
let
    Source = Parquet.Document(File.Contents(DataFolder & "quarantine.parquet"))
in
    Source


// ---- query name: dim_route ---------------------------------------------------------
let
    Source = Parquet.Document(File.Contents(DataFolder & "dim_route.parquet"))
in
    Source


// ---- query name: dim_site ----------------------------------------------------------
let
    Source = Parquet.Document(File.Contents(DataFolder & "dim_site.parquet"))
in
    Source


// ---- query name: dim_carrier -------------------------------------------------------
let
    Source = Parquet.Document(File.Contents(DataFolder & "dim_carrier.parquet"))
in
    Source


// ---- query name: dim_airport -------------------------------------------------------
let
    Source = Parquet.Document(File.Contents(DataFolder & "dim_airport.parquet"))
in
    Source


// ---- query name: dim_date ----------------------------------------------------------
let
    Source = Parquet.Document(File.Contents(DataFolder & "dim_date.parquet"))
in
    Source


// ---- query name: user_access -------------------------------------------------------
let
    Source = Parquet.Document(File.Contents(DataFolder & "user_access.parquet"))
in
    Source
