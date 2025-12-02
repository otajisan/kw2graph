'use client';

import React, { useState, useCallback, useTransition, useEffect, useRef } from 'react';
import axios, { AxiosError } from 'axios';
import styles from './page.module.css';

// APIのベースURL。FastAPIが動いているURLを指定
const API_BASE_URL = 'http://localhost:8000';

// --- 型定義 ---

// Candidate API 応答
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

// Analyze API 応答 (Python: AnalyzeKeywordsOutput)
interface AnalyzeKeywordsOutputItem {
    keyword: string;
    score: number;
}

interface AnalyzeKeywordsOutput {
    seed_keyword: string;
    results: AnalyzeKeywordsOutputItem[];
}

// Create Graph API 応答 (Python: CreateGraphOutput)
interface CreateGraphOutput {
    result: boolean;
}

// Create Graph API リクエスト (Python: CreateGraphInput)
interface CreateGraphInput {
    seed_keyword: string;
    children: { keyword: string; score: number }[];
}

// Show Graph API 応答 (Python: ShowGraphOutput)
interface GraphNode {
    id: string;
    label: string;
    group: string;
}

interface GraphEdge {
    id: string;
    from_node: string;
    to_node: string;
    score: number;
}

interface ShowGraphOutput {
    nodes: GraphNode[];
    edges: GraphEdge[];
}


// --- メインコンポーネント ---

export default function Home() {
    const [keyword, setKeyword] = useState<string>('');
    const [candidateData, setCandidateData] = useState<CandidateResponse | null>(null);
    const [analyzeData, setAnalyzeData] = useState<AnalyzeKeywordsOutput | null>(null);
    const [graphData, setGraphData] = useState<ShowGraphOutput | null>(null); // 💡 グラフデータ

    const [error, setError] = useState<string | null>(null);

    const [isPending, startTransition] = useTransition();
    const [isAnalyzePending, startAnalyzeTransition] = useTransition();
    const [isCreatePending, startCreateTransition] = useTransition();
    const [isGraphPending, startGraphTransition] = useTransition(); // 💡 グラフ描画ローディング

    const [createStatus, setCreateStatus] = useState<'idle' | 'success' | 'failure'>('idle');


    // --- API関数 ---

    const handleAxiosError = (err: unknown, apiName: string) => {
        if (axios.isAxiosError(err)) {
            const axiosError = err as AxiosError;
            const status = axiosError.response?.status;
            const data = axiosError.response?.data;
            const message = `HTTPエラー (${status}): ${data ? JSON.stringify(data) : axiosError.message}`;
            setError(`${apiName} APIリクエスト失敗: ${message}`);
        } else {
            setError(`予期せぬエラー: ${err instanceof Error ? err.message : '不明なエラー'}`);
        }
        console.error(`Axios Error (${apiName}):`, err);
    };


    // 1. Candidate API
    const fetchCandidate = useCallback(async (kw: string) => {
        setError(null);
        setCandidateData(null);
        setAnalyzeData(null);
        setGraphData(null); // グラフデータもクリア
        setCreateStatus('idle');

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
            handleAxiosError(err, 'Candidate');
        }
    }, []);

    // 2. Analyze API
    const fetchAnalyze = useCallback(async (seedKeyword: string, titles: string[]) => {
        setAnalyzeData(null);
        setGraphData(null);
        setCreateStatus('idle');
        setError(null);

        const payload = {
            seed_keyword: seedKeyword,
            children: titles,
        };

        try {
            const response = await axios.post<AnalyzeKeywordsOutput>(
                `${API_BASE_URL}/analyze`,
                payload,
                { headers: { 'Content-Type': 'application/json' } }
            );
            setAnalyzeData(response.data);
        } catch (err) {
            handleAxiosError(err, 'Analyze');
        }
    }, []);

    // 3. Create Graph API
    const fetchCreateGraph = useCallback(async (data: AnalyzeKeywordsOutput) => {
        setCreateStatus('idle');
        setError(null);

        const payload: CreateGraphInput = {
            seed_keyword: data.seed_keyword,
            children: data.results.map(item => ({
                keyword: item.keyword,
                score: item.score,
            })),
        };

        try {
            const response = await axios.post<CreateGraphOutput>(
                `${API_BASE_URL}/create`,
                payload,
                { headers: { 'Content-Type': 'application/json' } }
            );

            if (response.data.result === true) {
                setCreateStatus('success');
            } else {
                setCreateStatus('failure');
                setError('グラフ作成APIが失敗を返しました。');
            }

        } catch (err) {
            setCreateStatus('failure');
            handleAxiosError(err, 'Create Graph');
        }
    }, []);

    // 💡 4. Show Graph API
    const fetchShowGraph = useCallback(async (seedKeyword: string) => {
        setGraphData(null);
        setError(null);
        setCreateStatus('idle');

        // GETリクエストでクエリパラメータを使用
        const params = new URLSearchParams({ seed_keyword: seedKeyword });

        try {
            const response = await axios.get<ShowGraphOutput>(
                `${API_BASE_URL}/show_graph?${params.toString()}`,
                { headers: { 'Content-Type': 'application/json' } }
            );

            setGraphData(response.data);

        } catch (err) {
            handleAxiosError(err, 'Show Graph');
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

    const handleAnalyze = () => {
        if (!candidateData || candidateData.candidates.length === 0) {
            setError('Analyzeを実行するには、先にCandidate検索を実行し、結果を取得してください。');
            return;
        }

        const titles = candidateData.candidates.map(c => c.snippet.title);

        startAnalyzeTransition(() => {
            fetchAnalyze(candidateData.seed_keyword, titles);
        });
    };

    const handleCreateGraph = () => {
        if (!analyzeData || analyzeData.results.length === 0) {
            setError('Create Graphを実行するには、Analyze検索を実行し、結果を取得してください。');
            return;
        }

        startCreateTransition(() => {
            fetchCreateGraph(analyzeData);
        });
    };

    // 💡 Show Graph ボタンクリック時の処理
    const handleShowGraph = () => {
        if (!keyword.trim()) {
            setError('グラフ表示を実行するには、検索キーワードを入力してください。');
            return;
        }

        startGraphTransition(() => {
            fetchShowGraph(keyword);
        });
    };


    return (
        <div className={styles.page}>
            <main className={styles.main}>
                <h1>FastAPI連携プロトタイプ (Next.js x FastAPI)</h1>

                {/* キーワード入力 */}
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

                {/* ボタン群 */}
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', marginBottom: '40px' }}>
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

                    <button
                        onClick={handleAnalyze}
                        disabled={!candidateData || isAnalyzePending || isPending || isCreatePending || isGraphPending}
                        style={{
                            padding: '10px 20px',
                            fontSize: '16px',
                            cursor: 'pointer',
                            backgroundColor: isAnalyzePending ? '#ffdd99' : '#ff9800',
                            color: 'white',
                            border: 'none',
                            borderRadius: '5px',
                            fontWeight: 'bold'
                        }}
                    >
                        {isAnalyzePending ? 'Analyze中...' : 'Analyze Titles'}
                    </button>

                    <button
                        onClick={handleCreateGraph}
                        disabled={!analyzeData || isCreatePending || isPending || isAnalyzePending || isGraphPending}
                        style={{
                            padding: '10px 20px',
                            fontSize: '16px',
                            cursor: 'pointer',
                            backgroundColor: isCreatePending ? '#a5d6a7' : '#4caf50',
                            color: 'white',
                            border: 'none',
                            borderRadius: '5px',
                            fontWeight: 'bold'
                        }}
                    >
                        {isCreatePending ? '登録中...' : 'Create Graph'}
                    </button>

                    {/* 💡 Show Graph ボタン */}
                    <button
                        onClick={handleShowGraph}
                        disabled={!keyword.trim() || isGraphPending || isPending || isAnalyzePending || isCreatePending}
                        style={{
                            padding: '10px 20px',
                            fontSize: '16px',
                            cursor: 'pointer',
                            backgroundColor: isGraphPending ? '#00bcd4' : '#0097a7',
                            color: 'white',
                            border: 'none',
                            borderRadius: '5px',
                            fontWeight: 'bold'
                        }}
                    >
                        {isGraphPending ? '描画中...' : 'Show Graph'}
                    </button>
                </div>

                <hr style={{ width: '100%', margin: '40px 0', borderColor: '#eee' }} />

                {/* --- 結果表示エリア --- */}

                {/* Create 結果のメッセージ表示 */}
                <CreateResultDisplay status={createStatus} />

                {/* 💡 グラフ描画エリア */}
                {isGraphPending && <p style={{ color: '#0097a7' }}>グラフデータをFastAPIから取得中です...</p>}
                {graphData && graphData.nodes.length > 0 && (
                    <GraphVisualizationComponent data={graphData} />
                )}
                {graphData && graphData.nodes.length === 0 && !isGraphPending && (
                    <div style={{ padding: '15px', backgroundColor: '#e0f7fa', border: '1px solid #0097a7', color: '#333', borderRadius: '4px', marginBottom: '20px' }}>
                        <p style={{ margin: 0, fontWeight: 'bold' }}>ℹ️ グラフデータが見つかりませんでした。</p>
                        <p style={{ margin: 0, fontSize: '0.9em' }}>キーワード「{keyword}」に関連するノードとエッジは登録されていません。</p>
                    </div>
                )}

                {/* Analyze結果の表示 */}
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
// Create 結果表示コンポーネント (変更なし)
// ----------------------------------------
interface CreateResultDisplayProps {
    status: 'idle' | 'success' | 'failure';
}

const CreateResultDisplay: React.FC<CreateResultDisplayProps> = ({ status }) => {
    if (status === 'success') {
        return (
            <div style={{
                padding: '15px',
                backgroundColor: '#e8f5e9',
                border: '1px solid #4caf50',
                color: '#333',
                borderRadius: '4px',
                marginBottom: '20px'
            }}>
                <p style={{ margin: 0, fontWeight: 'bold' }}>🎉 登録成功!</p>
                <p style={{ margin: 0, fontSize: '0.9em' }}>グラフ作成リクエストが FastAPI によって正常に処理されました。</p>
            </div>
        );
    }

    if (status === 'failure') {
        return (
            <div style={{
                padding: '15px',
                backgroundColor: '#ffebee',
                border: '1px solid #f44336',
                color: '#f44336',
                borderRadius: '4px',
                marginBottom: '20px'
            }}>
                <p style={{ margin: 0, fontWeight: 'bold' }}>❌ 登録失敗</p>
                <p style={{ margin: 0, fontSize: '0.9em' }}>詳細については、画面下部のエラーメッセージを確認してください。</p>
            </div>
        );
    }

    return null;
};


// ----------------------------------------
// Analyze結果表示コンポーネント (修正済み)
// ----------------------------------------

interface AnalyzeResultDisplayProps {
    data: AnalyzeKeywordsOutput;
}

const AnalyzeResultDisplay: React.FC<AnalyzeResultDisplayProps> = ({ data }) => {
    if (!data.results || data.results.length === 0) {
        return (
            <div style={{ padding: '20px', backgroundColor: '#fffbe6', border: '1px solid #ffcc00', borderRadius: '5px', color: '#333' }}>
                <p>🔍 キーワード「{data.seed_keyword}」に対する分析結果は見つかりませんでした。</p>
            </div>
        );
    }

    return (
        <div style={{
            width: '100%',
            maxWidth: '800px',
            margin: '20px auto 40px auto',
            padding: '20px',
            backgroundColor: '#fff3e0',
            border: '2px solid #ff9800',
            borderRadius: '8px',
            boxShadow: '0 4px 6px rgba(0,0,0,0.1)',
            color: '#333'
        }}>
            <h3 style={{ color: '#333' }}>📊 キーワード分析結果 (シードキーワード: {data.seed_keyword})</h3>

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
                                color: '#333'
                            }}
                        >
                            <span style={{ fontWeight: 'bold' }}>{index + 1}. {item.keyword}</span>
                            <span style={{ color: item.score > 0.7 ? '#d32f2f' : '#ff9800', fontWeight: 'bold' }}>
                           スコア: {item.score.toFixed(3)}
                        </span>
                        </li>
                    ))}
            </ul>
        </div>
    );
};

// ----------------------------------------
// Candidate結果表示コンポーネント (修正済み)
// ----------------------------------------

interface CandidateResultDisplayProps {
    data: CandidateResponse;
}

const CandidateResultDisplay: React.FC<CandidateResultDisplayProps> = ({ data }) => {
    if (!data.candidates || data.candidates.length === 0) {
        return (
            <div style={{ padding: '20px', backgroundColor: '#fffbe6', border: '1px solid #ffcc00', borderRadius: '5px', color: '#333' }}>
                <p>🔍 キーワード「{data.seed_keyword}」に対する候補は見つかりませんでした。</p>
            </div>
        );
    }

    return (
        <div style={{ width: '100%', maxWidth: '800px', margin: '20px auto 0 auto' }}>
            <h2 style={{ color: '#333' }}>✅ Candidate 検索結果</h2>

            <div style={{ marginBottom: '15px', padding: '10px', backgroundColor: '#e8f5e9', borderLeft: '5px solid #4caf50' }}>
                <p style={{ margin: 0, color: '#333' }}>
                    リクエストキーワード: <span style={{ fontWeight: 'bold' }}>{data.seed_keyword}</span> (全 {data.candidates.length} 件)
                </p>
            </div>

            <ul style={{ listStyle: 'none', padding: 0 }}>
                {data.candidates.map((candidate, index) => (
                    <li
                        key={candidate.videoId}
                        style={{
                            padding: '12px 15px',
                            marginBottom: '8px',
                            backgroundColor: '#ffffff',
                            border: '1px solid #ddd',
                            borderRadius: '4px',
                            boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
                            display: 'flex',
                            alignItems: 'flex-start',
                            color: '#333'
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
                        <a
                            href={`https://www.youtube.com/watch?v=${candidate.videoId}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{
                                color: '#1a0dab',
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
// 💡 グラフ描画コンポーネント
// ----------------------------------------

interface GraphVisualizationComponentProps {
    data: ShowGraphOutput;
}

const GraphVisualizationComponent: React.FC<GraphVisualizationComponentProps> = ({ data }) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const [isVisLoaded, setIsVisLoaded] = useState(false);

    // 💡 vis.js の CDN ロード
    useEffect(() => {
        const scriptId = 'vis-js-script';
        // スクリプトが既に存在するかチェック
        if (!(window as any).vis && !document.getElementById(scriptId)) {
            const script = document.createElement('script');
            script.src = 'https://cdnjs.cloudflare.com/ajax/libs/vis/4.21.0/vis.min.js';
            script.async = true;
            script.id = scriptId;
            script.onload = () => setIsVisLoaded(true);
            document.head.appendChild(script);

            const styleLink = document.createElement('link');
            styleLink.rel = 'stylesheet';
            styleLink.href = 'https://cdnjs.cloudflare.com/ajax/libs/vis/4.21.0/vis.min.css';
            document.head.appendChild(styleLink);
        } else if ((window as any).vis) {
            setIsVisLoaded(true);
        }
    }, []);

    // 💡 グラフ描画ロジック
    useEffect(() => {
        if (!isVisLoaded || !containerRef.current || data.nodes.length === 0) {
            return;
        }

        const vis = (window as any).vis;
        if (!vis) return; // vis.js がロードされていない場合は中断

        // 1. vis.js のデータ形式に変換
        // FastAPIの 'from_node', 'to_node' を vis.js の 'from', 'to' にマッピング
        const nodes = new vis.DataSet(data.nodes);
        const edges = new vis.DataSet(data.edges.map(edge => ({
            id: edge.id,
            from: edge.from_node,
            to: edge.to_node,
            value: edge.score * 10, // スコアをエッジの太さに使う (可視化のためスケーリング)
            title: `Score: ${edge.score.toFixed(3)}` // ホバー表示
        })));

        const graphData = { nodes, edges };
        const options = {
            nodes: {
                shape: 'dot',
                size: 20,
                font: {
                    size: 14,
                    color: '#333'
                },
                borderWidth: 2
            },
            edges: {
                width: 2,
                arrows: 'to',
                color: { inherit: 'from' },
                smooth: {
                    type: 'continuous'
                }
            },
            // キーワードのグルーピングに合わせて色分け
            groups: {
                seed: { color: { background: '#FFC107', border: '#FF9800' }, size: 30 },
                related: { color: { background: '#2196F3', border: '#1976D2' } },
                // 他のグループがあればここに追加
            },
            physics: {
                enabled: true,
                barnesHut: {
                    gravitationalConstant: -2000,
                    centralGravity: 0.3,
                    springLength: 95,
                    springConstant: 0.04,
                    damping: 0.09,
                    avoidOverlap: 0.5
                },
                solver: 'barnesHut',
                stabilization: {
                    enabled: true,
                    iterations: 2500,
                    updateInterval: 25
                }
            },
            height: '500px'
        };

        // 2. ネットワーク描画
        const network = new vis.Network(containerRef.current, graphData, options);

        // クリーンアップ関数
        return () => {
            network.destroy();
        };
    }, [isVisLoaded, data]);

    if (!isVisLoaded) {
        return <p style={{ color: '#333' }}>グラフ描画ライブラリをロード中です...</p>;
    }

    return (
        <div style={{ width: '100%', maxWidth: '800px', margin: '20px auto', color: '#333' }}>
            <h2 style={{ color: '#333' }}>📈 グラフ表示</h2>
            <div
                ref={containerRef}
                style={{
                    width: '100%',
                    height: '500px',
                    border: '1px solid #ddd',
                    borderRadius: '8px',
                    backgroundColor: '#f5f5f5' // グラフ背景を灰色で明確に
                }}
            >
                {/* グラフがここに描画されます */}
                {data.nodes.length === 0 && <p style={{ textAlign: 'center', paddingTop: '200px', color: '#666' }}>表示するグラフデータがありません。</p>}
            </div>
            <p style={{ fontSize: '0.9em', color: '#666', marginTop: '10px' }}>ノードをドラッグしてレイアウトを変更できます。エッジの太さは関連度スコアを表します。</p>
        </div>
    );
};

// ... (残りのコンポーネント定義)
