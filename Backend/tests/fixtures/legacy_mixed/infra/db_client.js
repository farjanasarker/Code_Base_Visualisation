function queryDatabase(table, params, op) {
  return { table, params, op };
}

module.exports = { queryDatabase };
