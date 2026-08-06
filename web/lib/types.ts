export type Toxicity = {
  score: number;      // 0-100
  is_toxic: boolean;
  language: string;   // ISO 639-1, or "und"
  threshold: number;  // the cut-off applied for that language
};

export type Post = {
  id: string;
  text: string;
  created_at: string;
  favorite_count: number;
  retweet_count: number;
  url: string;
  media: { type: string; url: string }[];
  toxicity: Toxicity;
};

export type ProfileUser = {
  name: string;
  screen_name: string;
  avatar: string;
  followers_count: number;
  following_count: number;
};

export type Summary = {
  total: number;
  toxic: number;
  safe: number;
  toxic_ratio: number;
  average_score: number;
  languages: Record<string, number>;
};

export type ModelInfo = {
  backend: string;
  model_id: string | null;
  languages: string[];
  n_samples: number | null;
  macro_f1: number | null;
  accuracy: number | null;
  roc_auc: number | null;
  global_threshold: number;
  trained_at: string | null;
};

export type ProfileResponse = {
  user: ProfileUser;
  summary: Summary;
  model: ModelInfo;
  posts: Post[];
};

export type AnalyzeResult = Toxicity & { text: string };
