'use client';

import { useState, useCallback, useTransition, useMemo } from 'react';
import axios, { AxiosError } from 'axios';
import styles from './page.module.css';

const API_BASE_URL = 'http://localhost:8000';

// FastAPIからのCandidateレスポンスの型定義（前回と同じ）
interface Candidate {
    videoId: string;
    snippet: {
        title: string;
    };
}

interface CandidateResponse {
    seed_keyword: string;
    candidates: Candidate[];
}

interface AnalyzeKeywordsOutputItem {
    keyword: string; // 抽出されたキーワード
    score: number;   // 関連度スコア (float)
}

interface AnalyzeKeywordsOutput {
    seed_keyword: string;
    results: AnalyzeKeywordsOutputItem[]; // 💡 キー名が 'extracted_keywords' や 'candidates' ではなく 'results' である点に注意
}

export default function Home() {
    const [keyword, setKeyword] = useState<string>('');
    const [candidateData, setCandidateData] = useState<CandidateResponse | null>(null);
    const [analyzeData, setAnalyzeData] = useState<AnalyzeKeywordsOutput | null>(null); // Analyze結果のState
    const [error, setError] = useState<string | null>(null);
    const [isPending, startTransition] = useTransition();
    const [isAnalyzePending, startAnalyzeTransition] = useTransition(); // Analyze用のローディングState

    // --- API関数 ---

    // Candidate API (前回のPOST実装)
    const fetchCandidate = useCallback(async (kw: string) => {
        setError(null);
        setCandidateData(null);
        setAnalyzeData(null); // 新しい検索の前にAnalyze結果をクリア

        const payload = {
            index: 'videos',
            field: 'snippet.title',
            keyword: kw,
        };

        try {
            const response = await axios.post<CandidateResponse>(
                `${API_BASE_URL}/candidate`,
                payload,
                { headers: { 'Content-Type': 'application/json' } }
            );
            setCandidateData(response.data);
        } catch (err) {
            // ... (エラー処理は省略)
            if (axios.isAxiosError(err)) {
                const axiosError = err as AxiosError;
                const status = axiosError.response?.status;
                const data = axiosError.response?.data;
                const message = `HTTPエラー (${status}): ${data ? JSON.stringify(data) : axiosError.message}`;
                setError(`APIリクエスト失敗: ${message}`);
            } else {
                setError(`予期せぬエラー: ${err instanceof Error ? err.message : '不明なエラー'}`);
            }
        }
    }, []);

    // 💡 Analyze API (新しい POST 実装)
    const fetchAnalyze = useCallback(async (seedKeyword: string, titles: string[]) => {
        setAnalyzeData(null);
        setError(null);

        const payload = {
            seed_keyword: seedKeyword,
            children: titles, // titleのリスト
        };

        try {
            // 💡 応答の型を AnalyzeKeywordsOutput に変更
            const response = await axios.post<AnalyzeKeywordsOutput>(
                `${API_BASE_URL}/analyze`,
                payload,
                { headers: { 'Content-Type': 'application/json' } }
            );
            // 💡 Stateを AnalyzeKeywordsOutput 型として設定
            setAnalyzeData(response.data);
        } catch (err) {
            // ... (エラー処理は省略)
            if (axios.isAxiosError(err)) {
                const axiosError = err as AxiosError;
                const status = axiosError.response?.status;
                const data = axiosError.response?.data;
                const message = `HTTPエラー (${status}): ${data ? JSON.stringify(data) : axiosError.message}`;
                setError(`Analyze APIリクエスト失敗: ${message}`);
            } else {
                setError(`予期せぬエラー: ${err instanceof Error ? err.message : '不明なエラー'}`);
            }
        }
    }, []);

    // --- イベントハンドラ ---

    const handleGetCandidate = () => {
        if (!keyword.trim()) {
            setError('キーワードを入力してください。');
            return;
        }
        startTransition(() => {
            fetchCandidate(keyword);
        });
    };

    // 💡 Analyze ボタンクリック時の処理
    const handleAnalyze = () => {
        if (!candidateData || candidateData.candidates.length === 0) {
            setError('Analyzeを実行するには、先にCandidate検索を実行し、結果を取得してください。');
            return;
        }

        // レスポンスからsnippet.titleのリストを抽出
        const titles = candidateData.candidates.map(c => c.snippet.title);

        startAnalyzeTransition(() => {
            fetchAnalyze(candidateData.seed_keyword, titles);
        });
    };

    return (
        <div className={styles.page}>
            <main className={styles.main}>
                <h1>FastAPI連携プロトタイプ (Next.js x FastAPI)</h1>

                {/* キーワード入力とボタン */}
                <div style={{ marginBottom: '20px' }}>
                    <label htmlFor="keyword-input" style={{ display: 'block', marginBottom: '8px', fontWeight: 'bold' }}>
                        検索キーワード:
                    </label>
                    <input
                        id="keyword-input"
                        type="text"
                        value={keyword}
                        onChange={(e) => setKeyword(e.target.value)}
                        placeholder="例: 料理"
                        style={{ padding: '10px', fontSize: '16px', minWidth: '300px', border: '1px solid #ccc', borderRadius: '4px' }}
                        disabled={isPending}
                    />
                </div>

                <div style={{ display: 'flex', gap: '20px', marginBottom: '40px' }}>
                    <button
                        onClick={handleGetCandidate}
                        disabled={isPending || !keyword.trim()}
                        style={{
                            padding: '10px 20px',
                            fontSize: '16px',
                            cursor: 'pointer',
                            backgroundColor: isPending ? '#99d9ff' : '#0070f3',
                            color: 'white',
                            border: 'none',
                            borderRadius: '5px',
                            fontWeight: 'bold'
                        }}
                    >
                        {isPending ? '検索中...' : 'Get Candidate'}
                    </button>

                    {/* 💡 Analyzeボタンの追加 */}
                    <button
                        onClick={handleAnalyze}
                        // Candidateデータがあり、Analyze処理中でない場合に有効化
                        disabled={!candidateData || isAnalyzePending || isPending}
                        style={{
                            padding: '10px 20px',
                            fontSize: '16px',
                            cursor: 'pointer',
                            backgroundColor: isAnalyzePending ? '#ffdd99' : '#ff9800', // Analyzeボタンの色
                            color: 'white',
                            border: 'none',
                            borderRadius: '5px',
                            fontWeight: 'bold'
                        }}
                    >
                        {isAnalyzePending ? 'Analyze中...' : 'Analyze Titles'}
                    </button>
                </div>

                <hr style={{ width: '100%', margin: '40px 0', borderColor: '#eee' }} />

                {/* --- 結果表示エリア --- */}

                {/* 💡 Analyze結果の表示 */}
                {isAnalyzePending && <p style={{ color: '#ff9800' }}>AnalyzeデータをFastAPIで処理中です...</p>}
                {analyzeData && (
                    <AnalyzeResultDisplay data={analyzeData} />
                )}

                {/* Candidate結果の表示 */}
                {candidateData && (
                    <CandidateResultDisplay data={candidateData} />
                )}

                {/* エラー表示は一番下に */}
                {error && (
                    <div style={{ color: 'white', backgroundColor: '#e33e3e', border: '1px solid #a00', padding: '15px', borderRadius: '5px', marginTop: '20px' }}>
                        <strong>🚨 エラーが発生しました:</strong>
                        <pre style={{ whiteSpace: 'pre-wrap', margin: '5px 0 0 0', fontSize: '14px' }}>
                {error}
            </pre>
                    </div>
                )}
            </main>
        </div>
    );
}

// ----------------------------------------
// Candidate結果表示コンポーネント (前回と同じ)
// ----------------------------------------

interface CandidateResultDisplayProps {
    data: CandidateResponse;
}

const CandidateResultDisplay: React.FC<CandidateResultDisplayProps> = ({ data }) => {
    // 候補がない場合の処理は変更なし...

    return (
        <div style={{ width: '100%', maxWidth: '800px', margin: '20px auto 0 auto' }}>
            {/* 💡 h2タグの文字色を固定 */}
            <h2 style={{ color: '#333' }}>✅ Candidate 検索結果</h2>

            {/* キーワード表示部分の修正 */}
            <div style={{ marginBottom: '15px', padding: '10px', backgroundColor: '#e8f5e9', borderLeft: '5px solid #4caf50' }}>
                <p style={{ margin: 0, color: '#333' }}> {/* 💡 文字色を固定 */}
                    リクエストキーワード: <span style={{ fontWeight: 'bold' }}>{data.seed_keyword}</span> (全 {data.candidates.length} 件)
                </p>
            </div>

            <ul style={{ listStyle: 'none', padding: 0 }}>
                {data.candidates.map((candidate, index) => (
                    <li
                        key={candidate.videoId}
                        style={{
                            // ... (スタイルの変更なし)
                            padding: '12px 15px',
                            marginBottom: '8px',
                            backgroundColor: '#ffffff',
                            border: '1px solid #ddd',
                            borderRadius: '4px',
                            boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
                            display: 'flex',
                            alignItems: 'flex-start',
                            color: '#333' // 💡 li内の文字色も確実に継承
                        }}
                    >
                        <span style={{
                            fontWeight: 'bold',
                            marginRight: '10px',
                            color: '#0070f3',
                            fontSize: '1.1em'
                        }}>
                            {index + 1}.
                        </span>
                        {/* aタグ内のスタイルは変更なし (リンクはブラウザ標準の色で表示) */}
                        <a
                            href={`https://www.youtube.com/watch?v=${candidate.videoId}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{
                                color: '#1a0dab', // 💡 リンク色は濃い青で固定
                                textDecoration: 'none',
                                flexGrow: 1
                            }}
                            onMouseEnter={(e) => e.currentTarget.style.textDecoration = 'underline'}
                            onMouseLeave={(e) => e.currentTarget.style.textDecoration = 'none'}
                        >
                            {candidate.snippet.title}
                        </a>
                    </li>
                ))}
            </ul>
        </div>
    );
};


// ----------------------------------------
// 💡 新しい Analyze結果表示コンポーネント
// ----------------------------------------

interface AnalyzeResultDisplayProps {
    data: AnalyzeKeywordsOutput; // 💡 新しい型を適用
}

const AnalyzeResultDisplay: React.FC<AnalyzeResultDisplayProps> = ({ data }) => {
    // 候補がない場合の処理は変更なし...
    if (!data.results || data.results.length === 0) {
        return (
            <div style={{ padding: '20px', backgroundColor: '#fffbe6', border: '1px solid #ffcc00', borderRadius: '5px' }}>
                <p style={{ color: '#333' }}>🔍 キーワード「{data.seed_keyword}」に対する分析結果は見つかりませんでした。</p>
            </div>
        );
    }

    return (
        <div style={{
            width: '100%',
            maxWidth: '800px',
            margin: '0 auto 40px auto',
            padding: '20px',
            backgroundColor: '#fff3e0', // 背景色を薄いオレンジ系（修正なし）
            border: '2px solid #ff9800',
            borderRadius: '8px',
            boxShadow: '0 4px 6px rgba(0,0,0,0.1)',
            color: '#333' // 💡 全体の文字色を濃い灰色（ほぼ黒）に固定
        }}>
            {/* 💡 h3タグの文字色も継承 */}
            <h3>📊 キーワード分析結果 (シードキーワード: {data.seed_keyword})</h3>

            <ul style={{ listStyle: 'none', padding: 0 }}>
                {data.results
                    .sort((a, b) => b.score - a.score)
                    .map((item, index) => (
                        <li
                            key={item.keyword}
                            style={{
                                display: 'flex',
                                justifyContent: 'space-between',
                                padding: '10px 0',
                                borderBottom: '1px dashed #ffd740',
                                // 💡 li内の文字色も確実に継承
                                color: '#333'
                            }}
                        >
                            {/* 💡 キーワードはボールドスタイルを直接適用 */}
                            <span style={{ fontWeight: 'bold' }}>{index + 1}. {item.keyword}</span>
                            {/* 💡 スコアにもボールドスタイルを直接適用 */}
                            <span style={{ color: item.score > 0.7 ? '#d32f2f' : '#ff9800', fontWeight: 'bold' }}>
                           スコア: {item.score.toFixed(3)}
                        </span>
                        </li>
                    ))}
            </ul>
        </div>
    );
};
