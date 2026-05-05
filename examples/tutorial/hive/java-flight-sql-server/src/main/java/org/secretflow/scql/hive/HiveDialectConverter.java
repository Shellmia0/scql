package org.secretflow.scql.hive;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;

final class HiveDialectConverter {
  private static final Pattern MYSQL_SIGNED_CAST_PATTERN =
      Pattern.compile(
          "\\bCAST\\s*\\((.+?)\\s+AS\\s+(?:SIGNED|UNSIGNED)(?:\\s+INTEGER)?\\s*\\)",
          Pattern.CASE_INSENSITIVE);
  private static final Pattern MYSQL_STRING_CAST_PATTERN =
      Pattern.compile(
          "\\bCAST\\s*\\((.+?)\\s+AS\\s+(?:VARCHAR|CHAR)(?:\\s*\\(\\s*\\d+\\s*\\))?\\s*\\)",
          Pattern.CASE_INSENSITIVE);
  private static final Pattern CURDATE_PATTERN =
      Pattern.compile("\\bCURDATE\\s*\\(\\s*\\)", Pattern.CASE_INSENSITIVE);
  private static final Pattern CURRENT_DATE_FN_PATTERN =
      Pattern.compile("\\bCURRENT_DATE\\s*\\(\\s*\\)", Pattern.CASE_INSENSITIVE);
  private static final Pattern NOW_PATTERN =
      Pattern.compile("\\bNOW\\s*\\(\\s*\\)", Pattern.CASE_INSENSITIVE);
  private static final Pattern CURRENT_TIMESTAMP_FN_PATTERN =
      Pattern.compile("\\bCURRENT_TIMESTAMP\\s*\\(\\s*\\)", Pattern.CASE_INSENSITIVE);
  private static final Pattern LAST_DAY_PATTERN =
      Pattern.compile("\\bLAST_DAY\\s*\\(([^()]+?)\\)", Pattern.CASE_INSENSITIVE);
  private static final Pattern STR_TO_DATE_PATTERN =
      Pattern.compile("\\bSTR_TO_DATE\\s*\\(([^,]+?),\\s*'([^']*)'\\s*\\)", Pattern.CASE_INSENSITIVE);
  private static final Pattern DATE_FORMAT_PATTERN =
      Pattern.compile("\\bDATE_FORMAT\\s*\\(([^,]+?),\\s*'([^']*)'\\s*\\)", Pattern.CASE_INSENSITIVE);
  private static final Pattern FROM_UNIXTIME_UNIX_TIMESTAMP_PATTERN =
      Pattern.compile("\\bFROM_UNIXTIME\\s*\\(\\s*UNIX_TIMESTAMP\\s*\\(([^,]+?),\\s*'([^']*)'\\s*\\)\\s*\\)", Pattern.CASE_INSENSITIVE);
  private static final Pattern DATE_ADD_PATTERN =
      Pattern.compile(
          "\\b(?:ADDDATE|DATE_ADD)\\s*\\(\\s*([^,]+?)\\s*,\\s*INTERVAL\\s+([^\\s,)]+)\\s+DAY\\s*\\)",
          Pattern.CASE_INSENSITIVE);
  private static final Pattern DATE_ADD_SIMPLE_PATTERN =
      Pattern.compile(
          "\\b(?:ADDDATE|DATE_ADD)\\s*\\(\\s*([^,]+?)\\s*,\\s*([^\\s,)]+)\\s*\\)",
          Pattern.CASE_INSENSITIVE);
  private static final Pattern DATE_SUB_PATTERN =
      Pattern.compile(
          "\\b(?:SUBDATE|DATE_SUB)\\s*\\(\\s*([^,]+?)\\s*,\\s*INTERVAL\\s+([^\\s,)]+)\\s+DAY\\s*\\)",
          Pattern.CASE_INSENSITIVE);
  private static final Pattern DATE_SUB_SIMPLE_PATTERN =
      Pattern.compile(
          "\\b(?:SUBDATE|DATE_SUB)\\s*\\(\\s*([^,]+?)\\s*,\\s*([^\\s,)]+)\\s*\\)",
          Pattern.CASE_INSENSITIVE);

  private final Pattern prefixPattern;

  HiveDialectConverter(String party, String database) {
    final List<String> prefixes =
        new ArrayList<>(Arrays.asList("alice", "bob", "default", "hive_demo"));
    if (party != null && !party.isEmpty()) {
      prefixes.add(party.toLowerCase(Locale.ROOT));
    }
    if (database != null && !database.isEmpty()) {
      prefixes.add(database.toLowerCase(Locale.ROOT));
    }
    this.prefixPattern =
        Pattern.compile("\\b(?:" + String.join("|", prefixes) + ")\\.", Pattern.CASE_INSENSITIVE);
  }

  String convert(String query) {
    String rewritten = query == null ? "" : query.trim();
    while (rewritten.endsWith(";")) {
      rewritten = rewritten.substring(0, rewritten.length() - 1).trim();
    }
    rewritten = prefixPattern.matcher(rewritten).replaceAll("");
    rewritten = rewritten.replaceAll("(?i)\\bIFNULL\\s*\\(", "COALESCE(");
    rewritten = NOW_PATTERN.matcher(rewritten).replaceAll("CURRENT_TIMESTAMP");
    rewritten = CURRENT_TIMESTAMP_FN_PATTERN.matcher(rewritten).replaceAll("CURRENT_TIMESTAMP");
    rewritten = CURDATE_PATTERN.matcher(rewritten).replaceAll("CURRENT_DATE");
    rewritten = CURRENT_DATE_FN_PATTERN.matcher(rewritten).replaceAll("CURRENT_DATE");
    rewritten = rewriteDateAddSub(rewritten, DATE_ADD_PATTERN, "DATE_ADD");
    rewritten = rewriteDateAddSub(rewritten, DATE_ADD_SIMPLE_PATTERN, "DATE_ADD");
    rewritten = rewriteDateAddSub(rewritten, DATE_SUB_PATTERN, "DATE_SUB");
    rewritten = rewriteDateAddSub(rewritten, DATE_SUB_SIMPLE_PATTERN, "DATE_SUB");
    rewritten = rewriteLastDay(rewritten);
    rewritten = rewriteStrToDate(rewritten);
    rewritten = rewriteFromUnixtimeUnixTimestamp(rewritten);
    rewritten = rewriteDateFormat(rewritten);
    rewritten = MYSQL_SIGNED_CAST_PATTERN.matcher(rewritten).replaceAll("CAST($1 AS BIGINT)");
    rewritten = MYSQL_STRING_CAST_PATTERN.matcher(rewritten).replaceAll("CAST($1 AS STRING)");
    return rewritten;
  }


  private String rewriteLastDay(String query) {
    return replaceAll(
        query,
        LAST_DAY_PATTERN,
        matcher -> "CAST(LAST_DAY(" + matcher.group(1).trim() + ") AS TIMESTAMP)");
  }

  private String rewriteStrToDate(String query) {
    return replaceAll(
        query,
        STR_TO_DATE_PATTERN,
        matcher ->
            "CAST(FROM_UNIXTIME(UNIX_TIMESTAMP("
                + matcher.group(1).trim()
                + ", '"
                + translateMySqlDateFormat(matcher.group(2))
                + "')) AS TIMESTAMP)");
  }

  private String rewriteFromUnixtimeUnixTimestamp(String query) {
    return replaceAll(
        query,
        FROM_UNIXTIME_UNIX_TIMESTAMP_PATTERN,
        matcher ->
            "CAST(FROM_UNIXTIME(UNIX_TIMESTAMP("
                + matcher.group(1).trim()
                + ", '"
                + translateMySqlDateFormat(matcher.group(2))
                + "')) AS TIMESTAMP)");
  }

  private String rewriteDateFormat(String query) {
    return replaceAll(
        query,
        DATE_FORMAT_PATTERN,
        matcher ->
            "DATE_FORMAT("
                + matcher.group(1).trim()
                + ", '"
                + translateMySqlDateFormat(matcher.group(2))
                + "')");
  }

  private String rewriteDateAddSub(String query, Pattern pattern, String funcName) {
    return replaceAll(
        query,
        pattern,
        matcher ->
            "CAST("
                + funcName
                + "("
                + matcher.group(1).trim()
                + ", "
                + matcher.group(2).trim()
                + ") AS TIMESTAMP)");
  }

  private static String replaceAll(
      String input,
      Pattern pattern,
      java.util.function.Function<java.util.regex.Matcher, String> rewriter) {
    java.util.regex.Matcher matcher = pattern.matcher(input);
    StringBuffer sb = new StringBuffer();
    while (matcher.find()) {
      matcher.appendReplacement(sb, java.util.regex.Matcher.quoteReplacement(rewriter.apply(matcher)));
    }
    matcher.appendTail(sb);
    return sb.toString();
  }

  private static String translateMySqlDateFormat(String fmt) {
    StringBuilder sb = new StringBuilder();
    for (int i = 0; i < fmt.length(); i++) {
      char ch = fmt.charAt(i);
      if (ch != '%' || i + 1 >= fmt.length()) {
        sb.append(ch);
        continue;
      }
      char token = fmt.charAt(++i);
      switch (token) {
        case 'Y':
          sb.append("yyyy");
          break;
        case 'y':
          sb.append("yy");
          break;
        case 'm':
          sb.append("MM");
          break;
        case 'c':
          sb.append('M');
          break;
        case 'd':
          sb.append("dd");
          break;
        case 'e':
          sb.append('d');
          break;
        case 'H':
          sb.append("HH");
          break;
        case 'k':
          sb.append('H');
          break;
        case 'h':
        case 'I':
          sb.append("hh");
          break;
        case 'l':
          sb.append('h');
          break;
        case 'i':
          sb.append("mm");
          break;
        case 's':
        case 'S':
          sb.append("ss");
          break;
        case 'p':
          sb.append('a');
          break;
        case 'M':
          sb.append("MMMM");
          break;
        case 'b':
          sb.append("MMM");
          break;
        case 'W':
          sb.append("EEEE");
          break;
        case 'a':
          sb.append("EEE");
          break;
        default:
          sb.append('%').append(token);
          break;
      }
    }
    return sb.toString();
  }
}
